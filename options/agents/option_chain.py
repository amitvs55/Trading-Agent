"""Option chain agent (pillar 6): OI walls, writing activity, PCR and max pain.

The chain is rebuilt from the recorded 1-minute option bars, so the live view and any
replay of a past day see exactly the same numbers.
"""

from dataclasses import dataclass, field
from datetime import date

from options.agents.context import AgentContext
from options.core.schemas import PillarView


@dataclass
class ChainRow:
    strike: float
    right: str
    token: int
    tradingsymbol: str
    lot_size: int
    ltp: float | None
    bid: float | None
    ask: float | None
    oi: float | None
    oi_open: float | None
    oi_15m: float | None
    oi_30m: float | None
    greeks: dict = field(default_factory=dict)    # iv, delta, gamma, vega, theta_day (Vol agent)

    @property
    def mid(self) -> float | None:
        if self.bid and self.ask and self.ask >= self.bid:
            return (self.bid + self.ask) / 2
        return self.ltp

    @property
    def spread_pct(self) -> float | None:
        m = self.mid
        if self.bid and self.ask and m:
            return (self.ask - self.bid) / m * 100
        return None


@dataclass
class Chain:
    expiry: date
    atm: float
    step: float
    rows: dict[tuple[float, str], ChainRow]

    def get(self, strike: float, right: str) -> ChainRow | None:
        return self.rows.get((strike, right))

    def strikes(self) -> list[float]:
        return sorted({k for k, _ in self.rows})


def build_chain(ctx: AgentContext, expiry: date, width: int = 15) -> Chain | None:
    spot = ctx.spot or ctx.fut
    if not spot or expiry not in ctx.ref.expiries:
        return None
    rows = {}
    for opt in ctx.ref.window(spot, width, n_expiries=len(ctx.ref.expiries)):
        if opt.expiry != expiry:
            continue
        last = ctx.state.last(opt.token)
        if last is None:
            continue
        rows[(opt.strike, opt.right)] = ChainRow(
            opt.strike, opt.right, opt.token, opt.tradingsymbol, opt.lot_size,
            ltp=last["close"], bid=last.get("bid"), ask=last.get("ask"), oi=last.get("oi"),
            oi_open=ctx.day_open_value(opt.token, "oi"),
            oi_15m=ctx.value_at(opt.token, "oi", 15), oi_30m=ctx.value_at(opt.token, "oi", 30))
    if not rows:
        return None
    return Chain(expiry, ctx.ref.atm_strike(spot, expiry), ctx.ref.strike_step, rows)


def _wall(chain: Chain, right: str, attr: str, above: bool) -> float | None:
    cands = [(getattr(r, attr) or 0, k) for (k, rt), r in chain.rows.items()
             if rt == right and (k >= chain.atm if above else k <= chain.atm)]
    best = max(cands, default=(0, None))
    return best[1] if best[0] > 0 else None


def max_pain(chain: Chain) -> float | None:
    strikes = chain.strikes()
    best = None
    for settle in strikes:
        pain = sum((r.oi or 0) * max(settle - k, 0) if rt == "CE" else (r.oi or 0) * max(k - settle, 0)
                   for (k, rt), r in chain.rows.items())
        if best is None or pain < best[0]:
            best = (pain, settle)
    return best[1] if best else None


def analyse(ctx: AgentContext, chain: Chain | None, expected_move: float | None = None) -> PillarView:
    if chain is None:
        return PillarView("option_chain", "No option chain data yet")

    band = max(5, min(15, round((expected_move or chain.step * 5) / chain.step)))
    near = {k: r for k, r in chain.rows.items() if abs(k[0] - chain.atm) <= band * chain.step}
    ce_oi = sum(r.oi or 0 for (k, rt), r in near.items() if rt == "CE")
    pe_oi = sum(r.oi or 0 for (k, rt), r in near.items() if rt == "PE")
    pcr = pe_oi / ce_oi if ce_oi else None

    # Writing activity in the last 15 minutes, ±3 strikes around ATM
    def d15(right: str) -> float:
        return sum((r.oi or 0) - (r.oi_15m or r.oi or 0) for (k, rt), r in chain.rows.items()
                   if rt == right and abs(k - chain.atm) <= 3 * chain.step)
    total_near = (ce_oi + pe_oi) or 1
    writing = (d15("PE") - d15("CE")) / total_near * 100     # + = puts written faster (bullish)

    call_wall, put_wall = _wall(chain, "CE", "oi", True), _wall(chain, "PE", "oi", False)
    call_wall_30, put_wall_30 = _wall(chain, "CE", "oi_30m", True), _wall(chain, "PE", "oi_30m", False)

    votes, notes = 0, []
    if writing > 2:
        votes += 1
        notes.append(f"put writing leads ({writing:+.1f}%)")
    elif writing < -2:
        votes -= 1
        notes.append(f"call writing leads ({writing:+.1f}%)")
    if put_wall and put_wall_30 and put_wall != put_wall_30:
        votes += 1 if put_wall > put_wall_30 else -1
        notes.append(f"put wall {put_wall_30:g}→{put_wall:g}")
    if call_wall and call_wall_30 and call_wall != call_wall_30:
        votes += 1 if call_wall > call_wall_30 else -1
        notes.append(f"call wall {call_wall_30:g}→{call_wall:g}")

    strength = min(1.0, abs(votes) / 2)
    if pcr and (pcr > 1.5 or pcr < 0.6):
        strength *= 0.6
        notes.append(f"PCR {pcr:.2f} stretched")
    elif pcr:
        notes.append(f"PCR {pcr:.2f}")
    walls = f"walls: put {put_wall:g} / call {call_wall:g}" if put_wall and call_wall else "walls forming"

    dte = ctx.calendar.trading_days_between(ctx.now.date(), chain.expiry)
    mp = max_pain(chain) if dte <= 2 else None
    if mp:
        notes.append(f"max pain {mp:g}")

    return PillarView("option_chain", " · ".join([walls] + notes),
                      bias=(1 if votes > 0 else -1 if votes < 0 else 0), strength=strength,
                      features={"pcr": pcr, "writing": writing, "call_wall": call_wall, "put_wall": put_wall,
                                "call_wall_30m": call_wall_30, "put_wall_30m": put_wall_30, "max_pain": mp})
