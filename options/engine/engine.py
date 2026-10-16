"""Signal engine: evaluates setups on every 5-minute close and manages open signals.

Every signal is saved before it is sent and never edited afterwards except by the
lifecycle, so the track record cannot be cherry-picked (plan §1).
"""

from datetime import datetime, time, timedelta
from typing import Callable

from options.agents import events as event_agent, macro as macro_agent
from options.agents.context import AgentContext, Constituent
from options.agents.health import AgentTracker
from options.agents.option_chain import build_chain
from options.agents.volatility import percentile_rank, price_chain
from options.config import OptionsSettings
from options.core.calendar import IST, MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.core.events import EVENTS, Event
from options.core.schemas import OPEN_STATES, Action, Contract, Grade, Signal, SignalState
from options.delivery import cards
from options.engine import confidence, grading, lifecycle, performance
from options.engine.levels import plan
from options.engine.risk import RiskConfig, budget_gate, size
from options.engine.selection import pick_expiry, pick_strike
from options.engine.snapshot import Snapshot, SnapshotError, take
from options.engine.state import MarketState
from options.notify.base import Notifier
from options.quant import indicators as ind
from options.reference import IndexReference
from options.setups import INTRADAY_SETUPS, POSITIONAL_SETUPS
from options.setups.base import Candidate, Setup
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("options.engine")

ID_PREFIX = {"NIFTY": "NF", "BANKNIFTY": "BN", "FINNIFTY": "FN"}
INTRADAY_TIME_STOP = time(14, 45)
SIGNAL_VALIDITY = timedelta(minutes=15)
POSITIONAL_CHECK = time(15, 20)          # daily-close invalidation check for positional signals
EVAL_DELAY_S = 4                         # evaluate once the bucket's last 1m bar has been flushed

Quote = tuple[float | None, float | None]


def bucket_end(now: datetime, minutes: int = 5) -> datetime | None:
    """End of the most recent completed `minutes` bucket counted from 09:15, if it just closed."""
    now = now.astimezone(IST)
    since_open = (now - at_ist(now.date(), MARKET_OPEN)).total_seconds()
    if since_open < minutes * 60:
        return None
    end = at_ist(now.date(), MARKET_OPEN) + timedelta(minutes=minutes * int(since_open // (minutes * 60)))
    return end if (now - end).total_seconds() >= EVAL_DELAY_S else None


class SignalEngine:
    def __init__(self, refs: dict[str, IndexReference], state: MarketState, store: Store, notifier: Notifier,
                 cfg: OptionsSettings, calendar: NseCalendar, *, vix_token: int | None = None,
                 constituents: dict[str, list[Constituent]] | None = None, vix_history: list[float] | None = None,
                 macro: Callable[[], dict | None] | None = None, events: list[Event] | None = None,
                 quote_fn: Callable[[int], Quote] | None = None, now_fn: Callable[[], datetime] = now_ist,
                 setups: list[Setup] | None = None):
        self.refs, self.state, self.store, self.notifier = refs, state, store, notifier
        self.cfg, self.calendar = cfg, calendar
        self.vix_token = vix_token
        self.constituents = constituents or {}
        self.vix_history = vix_history or []
        self.macro = macro or (lambda: None)
        self.events = EVENTS if events is None else events
        self.quote_fn = quote_fn
        self.now_fn = now_fn
        self.setups = INTRADAY_SETUPS + POSITIONAL_SETUPS if setups is None else setups
        self.risk = RiskConfig(cfg.OPTIONS_CAPITAL, cfg.OPTIONS_RISK_PER_TRADE_PCT, cfg.OPTIONS_DAILY_LOSS_STOP_PCT)
        self.open: list[Signal] = store.open_signals()          # positional signals survive overnight
        self._signalled: set[tuple] = set()
        self._flow_alerted: set[str] = set()
        self._last_bucket: datetime | None = None
        self.snapshots: dict[str, Snapshot] = {}
        self.agent_health: dict[str, AgentTracker] = {i: AgentTracker() for i in refs}

    # ── Inputs ───────────────────────────────────────────────────────────────

    def on_bars(self, rows: list[dict]) -> None:
        self.state.add_bars(rows)

    def quote(self, token: int) -> Quote:
        if self.quote_fn:
            bid, ask = self.quote_fn(token)
            if bid or ask:
                return bid, ask
        last = self.state.last(token)
        return (last.get("bid"), last.get("ask")) if last else (None, None)

    def context(self, index: str, now: datetime) -> AgentContext:
        return AgentContext(index, self.refs[index], self.state, now, self.calendar, vix_token=self.vix_token,
                            constituents=self.constituents.get(index, []), events=self.events,
                            vix_history=self.vix_history, macro=self.macro(), r=self.cfg.OPTIONS_RISK_FREE_RATE)

    # ── Main loop hook ───────────────────────────────────────────────────────

    def on_tick(self, now: datetime) -> None:
        for sig in list(self.open):
            bid, ask = self.quote(sig.contract.token)
            update = lifecycle.on_quote(sig, bid, ask, now)
            if update:
                self._apply(sig, update, now)
        end = bucket_end(now)
        if end and end != self._last_bucket:
            self._last_bucket = end
            self.evaluate(now)

    def evaluate(self, now: datetime) -> None:
        for index in self.refs:
            try:
                snap = take(self.context(index, now))
            except SnapshotError as e:                  # technical agent down: nothing to evaluate this time
                self._record_agents(index, e.runs, [r.agent for r in e.runs if r.status == "error"], now)
                continue
            self.snapshots[index] = snap
            self._record_agents(index, snap.runs, snap.failed, now)
            self.store.save_board(index, board(snap), now)
            self._manage_open(snap, now)
            if snap.failed:
                logger.warning("%s: no new signals this check, agent(s) failing: %s", index, ", ".join(snap.failed))
                continue
            self._scan(snap, now)

    def _record_agents(self, index: str, runs, failed: list[str], now: datetime) -> None:
        tracker = self.agent_health.setdefault(index, AgentTracker())
        for message in tracker.update(runs, now):
            self.notifier.send(f"{message} ({index})")
        try:
            self.store.save_agent_status(index, tracker.payload(now, failed), now)
        except Exception:                               # monitoring must never stop trading logic
            logger.exception("Couldn't save agent status for %s", index)

    # ── Open signals ─────────────────────────────────────────────────────────

    def _apply(self, sig: Signal, update: lifecycle.Update, now: datetime) -> None:
        self.store.save_signal(sig, now)
        self.store.signal_event(sig.signal_id, update.kind, update.price, update.message, now)
        if sig.state not in OPEN_STATES:
            self.open = [s for s in self.open if s.signal_id != sig.signal_id]
        if update.kind != "EXPIRED" or sig.mode == "LIVE":
            self.notifier.send(cards.update_message(sig, update.kind, update.message))

    def _manage_open(self, snap: Snapshot, now: datetime) -> None:
        index = snap.ctx.index
        for sig in [s for s in self.open if s.index == index]:
            bid, _ = self.quote(sig.contract.token)
            if sig.invalidation_tf == "5min":
                five = self.state.frame(sig.underlying_token, "5min")
                close = float(five["close"].iloc[-1]) if not five.empty else None
            elif now.time() >= POSITIONAL_CHECK or (sig.exit_by and now.date() >= sig.exit_by):
                close = self.state.last_price(sig.underlying_token)
            else:
                close = None
            update = lifecycle.on_close_check(sig, close, bid, now) if close is not None else None
            if update is None and sig.horizon == "intraday" and snap.events.next_event:
                nxt = snap.events.next_event
                if nxt.during_market and timedelta(0) <= nxt.at - now <= timedelta(minutes=30):
                    update = lifecycle.exit_now(sig, bid, now, "EVENT_EXIT")
            if update:
                self._apply(sig, update, now)
                continue
            if (sig.state in (SignalState.ACTIVE, SignalState.T1_HIT) and sig.signal_id not in self._flow_alerted
                    and snap.flow.bias == -sig.side and snap.flow.strength >= 0.6):
                self._flow_alerted.add(sig.signal_id)
                self.notifier.send(cards.update_message(sig, "FLOW", f"futures flow turned against the trade "
                                                        f"({snap.flow.detail.split(':')[0]}): consider tightening the stop"))

    # ── New signals ──────────────────────────────────────────────────────────

    def _scan(self, snap: Snapshot, now: datetime) -> None:
        for setup in self.setups:
            cand = setup.detect(snap)
            if cand is None:
                continue
            key = (now.date(), snap.ctx.index, setup.id, cand.side)
            if key in self._signalled:
                continue
            self._consider(snap, setup, cand, key, now)

    def _log(self, now, index, cand: Candidate, outcome, reasons, grade=None, score=None):
        self.store.log_evaluation(now, index, cand.setup, cand.side, grade, score, outcome, reasons)

    def _consider(self, snap: Snapshot, setup: Setup, cand: Candidate, key: tuple, now: datetime) -> None:
        ctx, index = snap.ctx, snap.ctx.index
        ref = ctx.ref
        expiry = pick_expiry(ref.expiries, now.date(), cand.horizon, self.calendar)
        chain = build_chain(ctx, expiry) if expiry else None
        if chain is None:
            return self._log(now, index, cand, "NO_TRADE", ["no tradable expiry or chain"])
        forward, t = price_chain(ctx, chain)
        row, why = pick_strike(chain, cand.side)
        if row is None:
            return self._log(now, index, cand, "NO_TRADE", [why])

        room = cand.room if cand.room_unit else snap.tech.room(cand.side, cand.trigger)[0]
        trade = plan(row, cand.side, cand.horizon, cand.trigger, cand.invalidation, forward, t, ctx.r, room)
        if trade is None:
            return self._log(now, index, cand, "NO_TRADE", ["could not price the contract"])

        positional = cand.horizon == "positional"
        sizing = size(self.risk, trade.entry_high, trade.stop, row.lot_size, positional)
        today_start = at_ist(now.date(), time(0, 0))
        todays = self.store.signals_since(today_start)
        realised = sum(s.pnl_rupees or 0 for s in todays if s.state is SignalState.CLOSED)
        open_risk = sum(s.risk_rupees for s in self.open)
        n_intraday = sum(s.horizon == "intraday" for s in self.open)
        reason = budget_gate(self.risk, realised, open_risk, sizing.risk_rupees, n_intraday,
                             len(self.open) - n_intraday, positional)

        pillar = grading.checks(snap, cand, row)
        gate_list = grading.gates(snap, cand, setup.regimes, pillar, trade, reason)
        grade, score, failed = grading.grade(pillar, gate_list)
        if failed:
            return self._log(now, index, cand, "NO_TRADE", failed, score=score)
        if grade is Grade.C:
            return self._log(now, index, cand, "GRADE_C", [f"score {score:.0f}"], "C", score)
        self._signalled.add(key)
        if sizing.over_budget:
            return self._log(now, index, cand, "OVER_BUDGET",
                             [f"1 lot risks ₹{sizing.risk_rupees:,.0f} > ₹{self.risk.per_trade_budget:,.0f} budget"],
                             grade.value, score)

        # An opposite grade-A signal ends any open trade in the other direction
        if grade is Grade.A:
            for other in [s for s in self.open if s.index == index and s.side == -cand.side and s.horizon == cand.horizon]:
                bid, _ = self.quote(other.contract.token)
                upd = lifecycle.exit_now(other, bid, now, "EXIT_SIGNAL")
                if upd:
                    self._apply(other, upd, now)

        seq = self.store.count_signals_on(today_start, today_start + timedelta(days=1)) + 1
        sig = self._build(snap, setup, cand, row, expiry, trade, sizing, grade, score, pillar, seq, now)
        self.store.save_signal(sig, now)
        self.store.signal_event(sig.signal_id, "CREATED", sig.entry_high, f"{sig.action.value} grade {grade.value}", now)
        self._log(now, index, cand, "SIGNAL", [sig.signal_id], grade.value, score)
        self.open.append(sig)

        everything = self.store.signals_since(today_start - timedelta(days=3650))
        st = performance.stats([s for s in everything if s.setup == setup.id])
        band = confidence.band_stats(everything).get(sig.grade.value)
        self.notifier.send(cards.signal_card(sig, self.risk.capital,
                                             performance.summary_line(st) if st["trades"] >= 30 else None,
                                             confidence.telegram_line(sig, band)))

    def _build(self, snap, setup, cand, row, expiry, trade, sizing, grade, score, pillar, seq, now) -> Signal:
        index = snap.ctx.index
        side = cand.side
        positional = cand.horizon == "positional"
        word = "below" if side > 0 else "above"
        rule = (f"{index} spot daily close {word} {cand.invalidation:,.0f}" if positional
                else f"{index} fut 5m close {word} {cand.invalidation:,.0f}")
        exit_by = None
        if positional:
            exit_by = self.calendar.next_trading_day(self.calendar.next_trading_day(now.date()))
        valid = now + SIGNAL_VALIDITY
        if positional:
            valid = min(valid, at_ist(now.date(), time(15, 25)))
        checks = grading.ordered(pillar)
        return Signal(
            signal_id=f"{ID_PREFIX.get(index, index[:2])}-{now:%y%m%d}-{seq:03d}",
            created_at=now, index=index, setup=setup.id, horizon=cand.horizon,
            action=Action.BUY_CE if side > 0 else Action.BUY_PE, grade=grade, score=round(score, 1),
            contract=Contract(index=index, tradingsymbol=row.tradingsymbol, token=row.token, expiry=expiry,
                              strike=row.strike, right=row.right, lot_size=row.lot_size),
            entry_low=trade.entry_low, entry_high=trade.entry_high, stop_loss=trade.stop,
            invalidation=round(cand.invalidation, 2), invalidation_rule=rule, invalidation_tf=cand.tf,
            underlying_token=cand.underlying_token, exit_by=exit_by,
            t1=trade.t1, t2=trade.t2, valid_until=valid, time_stop=None if positional else INTRADAY_TIME_STOP,
            lots=sizing.lots, risk_rupees=round(sizing.risk_rupees, 2), over_budget=sizing.over_budget,
            checks=checks, rationale=[c.detail for c in checks if c.status == "pass"][:5],
            mode="LIVE" if setup.id in self.cfg.OPTIONS_LIVE_SETUPS else "SHADOW",
        )

    def close_session(self, now: datetime) -> None:
        """Intraday signals never carry overnight: close at the last bid, or expire if unfilled."""
        for sig in [s for s in self.open if s.horizon == "intraday"]:
            bid, _ = self.quote(sig.contract.token)
            bid = bid or self.state.last_price(sig.contract.token)
            if sig.state is SignalState.TRIGGERED:
                sig.state, sig.closed_at, sig.exit_reason = SignalState.EXPIRED, now, "EXPIRED"
                update = lifecycle.Update("EXPIRED", None, "session ended before entry; no trade")
            elif bid:
                update = lifecycle.close(sig, bid, now, "SQUARE_OFF")
            else:
                logger.error("No price to square off %s; left open for review", sig.signal_id)
                continue
            self._apply(sig, update, now)

    # ── Daily messages ───────────────────────────────────────────────────────

    def morning_brief(self, now: datetime) -> str:
        sections = []
        for index, ref in self.refs.items():
            ctx = self.context(index, now)
            lines = []
            pd_ = self.state.prev_day(ref.spot_token)
            if pd_:
                piv = ind.cpr(pd_["high"], pd_["low"], pd_["close"])
                lines.append(f"Prev close {pd_['close']:,.0f} · high {pd_['high']:,.0f} / low {pd_['low']:,.0f}")
                lines.append(f"CPR {piv.bc:,.0f}–{piv.tc:,.0f} · R1 {piv.r1:,.0f} · S1 {piv.s1:,.0f}")
            vix = self.state.last_price(self.vix_token) if self.vix_token else None
            if vix:
                pct = percentile_rank(vix, self.vix_history)
                lines.append(f"India VIX {vix:.1f}" + (f" (1-year percentile {pct:.0f})" if pct is not None else ""))
            exp = ref.expiries[0] if ref.expiries else None
            if exp:
                tag = "today" if exp == now.date() else f"{exp:%a %d %b}"
                lines.append(f"Nearest expiry {tag}" + (" · monthly expiry" if exp == ref.future_expiry else ""))
            mv = macro_agent.analyse(ctx)
            if mv.status != "na":
                lines.append(f"Global: {mv.detail}")
            todays = [e for e in self.events if e.at.astimezone(IST).date() == now.date()]
            lines.append("Events: " + (", ".join(f"{e.name} {e.at:%H:%M}" for e in todays) if todays else "none today"))
            ev = event_agent.analyse(ctx)
            if ev.blocks_positional and ev.next_event:
                lines.append(f"No positional signals before {ev.next_event.name} ({ev.next_event.at:%d %b})")
            sections.append({"title": index, "lines": lines})
        return cards.morning_brief(now.date(), sections)

    def end_of_day(self, now: datetime) -> str:
        today_start = at_ist(now.date(), time(0, 0))
        todays = self.store.signals_since(today_start)
        everything = self.store.signals_since(today_start - timedelta(days=3650))
        overall = performance.summary_line(performance.stats(everything))
        setups = {k: performance.summary_line(v) for k, v in performance.by(everything, "setup").items()}
        levels = []
        for index, ref in self.refs.items():
            today = self.state.today(ref.spot_token, "1min")
            if not today.empty:
                h, l, c = float(today["high"].max()), float(today["low"].min()), float(today["close"].iloc[-1])
                piv = ind.cpr(h, l, c)
                levels.append(f"{index}: close {c:,.0f} · CPR {piv.bc:,.0f}–{piv.tc:,.0f} · "
                              f"R1 {piv.r1:,.0f} · S1 {piv.s1:,.0f}")
        return cards.eod_report(now.date(), todays, overall, setups, levels)


def board(snap: Snapshot) -> dict:
    """Serializable view of every pillar for the dashboard."""
    t, ctx = snap.tech, snap.ctx
    return {
        "index": ctx.index,
        "as_of": ctx.now.isoformat(timespec="seconds"),
        "spot": ctx.spot, "fut": ctx.fut, "basis": snap.basis,
        "vix": snap.vol.vix, "vix_pct": snap.vol.vix_pct, "atm_iv": snap.vol.atm_iv,
        "expected_move_1d": snap.vol.expected_move_1d,
        "regime": snap.regime.regime, "phase": snap.regime.phase, "htf_trend": t.htf_trend,
        "expiry_day": snap.regime.expiry_day, "monthly_expiry": snap.regime.monthly_expiry,
        "nearest_expiry": ctx.ref.expiries[0].isoformat() if ctx.ref.expiries else None,
        "lot_size": ctx.ref.lot_size, "strike_step": ctx.ref.strike_step,
        "levels": {k: round(v, 2) for k, v in sorted(t.levels.items(), key=lambda kv: -kv[1])},
        "oi": {k: v for k, v in snap.oi.features.items() if v is not None},
        "pillars": [{"pillar": p.pillar, "bias": p.bias, "strength": round(p.strength, 2), "status": p.status,
                     "detail": p.detail} for p in snap.pillars()],
    }
