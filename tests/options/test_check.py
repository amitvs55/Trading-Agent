"""Option Check: reading a contract, the market facts, the money, the evidence, the record."""

import math
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import check as check_routes
from options.backtest.synthetic import CAL, IV, MONTHLY, TODAY, WEEKLY, build_market, save_market
from options.check import outcomes, report as rep
from options.check.facts import market_facts
from options.check.history import HistoryModel
from options.check.parse import parse_query, resolve
from options.check.worker import CheckWorker
from options.config import OptionsSettings
from options.core.calendar import IST, at_ist
from options.engine.snapshot import take
from options.quant import black76 as b76
from options.quant import vec
from options.storage import Store, make_engine
from tests.options.fixtures import ist

FAR = date(2026, 12, 29)


@pytest.fixture(scope="module")
def ctx():
    return build_market()


@pytest.fixture(scope="module")
def snap(ctx):
    return take(ctx)


def _atm(ctx, right="CE", expiry=None):
    expiry = expiry or ctx.ref.expiries[0]
    k = ctx.ref.atm_strike(ctx.spot, expiry)
    return ctx.ref.options[(expiry, k, right)]


# ── Reading what was typed ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,expiry,strike,right", [
    ("Nifty 19th Oct 25000 ce", WEEKLY, 25000, "CE"),
    ("NIFTY 19 OCT 25000 CE", WEEKLY, 25000, "CE"),
    ("nifty 19-10 25,000 call", WEEKLY, 25000, "CE"),
    ("25000 pe", WEEKLY, 25000, "PE"),                       # nearest live expiry, NIFTY by default
    ("nifty 25000 put next week", MONTHLY, 25000, "PE"),
    ("Oct 27 nifty 24950ce", MONTHLY, 24950, "CE"),
    ("nifty monthly 25100 c", MONTHLY, 25100, "CE"),
    ("2026-10-27 25000 PE", MONTHLY, 25000, "PE"),
])
def test_contracts_are_read_in_any_common_form(ctx, text, expiry, strike, right):
    res = resolve(parse_query(text, TODAY), {"NIFTY": ctx.ref}, ist(2026, 10, 16, 11, 0))
    assert res.problem is None and res.option is not None
    assert (res.option.expiry, res.option.strike, res.option.right) == (expiry, strike, right)


def test_wrong_or_missing_parts_get_a_clear_problem_and_real_suggestions(ctx):
    refs, now = {"NIFTY": ctx.ref}, ist(2026, 10, 16, 11, 0)
    odd = resolve(parse_query("nifty 19 oct 25010 ce", TODAY), refs, now)
    assert "isn't a listed strike" in odd.problem and {o.strike for o in odd.suggestions} == {25000, 25050}
    no_side = resolve(parse_query("nifty 19 oct 25000", TODAY), refs, now)
    assert no_side.problem == "CE (call) or PE (put)?" and {o.right for o in no_side.suggestions} == {"CE", "PE"}
    sunday = resolve(parse_query("nifty 18 oct 25000 ce", TODAY), refs, now)
    assert "no expiry on Sun 18 Oct" in sunday.problem and sunday.suggestions
    sensex = resolve(parse_query("sensex 80000 ce", TODAY), refs, now)
    assert "SENSEX options aren't covered yet" in sensex.problem


def test_an_expiry_that_has_passed_is_called_expired_and_the_default_moves_on(ctx):
    refs, after_close = {"NIFTY": ctx.ref}, ist(2026, 10, 19, 15, 45)
    gone = resolve(parse_query("Nifty 19th Oct 25000 ce", date(2026, 10, 19)), refs, after_close)
    assert gone.option is None and "has passed" in gone.problem and gone.suggestions[0].expiry == MONTHLY
    default = resolve(parse_query("25000 ce", date(2026, 10, 19)), refs, after_close)
    assert default.option.expiry == MONTHLY


# ── Market facts ─────────────────────────────────────────────────────────────

def test_facts_price_the_contract_and_check_every_pillar_for_its_direction(ctx, snap):
    opt = _atm(ctx, "CE")
    f = market_facts(snap, opt, "intraday", ctx.now)
    c = f["contract"]
    assert c["ask"] > c["bid"] > 0 and abs(c["iv"] - IV) < 0.01 and 0.3 < c["greeks"]["delta"] < 0.7
    assert f["side"] == 1 and f["plan"]["stop"] < f["plan"]["entry_high"] < f["plan"]["t1"] < f["plan"]["t2"]
    assert {p["pillar"] for p in f["pillars"]} >= {"trend", "futures_flow", "option_chain", "volatility", "option_quality"}
    assert f["forward_source"].startswith("put-call parity") and f["score"] is not None
    put = market_facts(snap, _atm(ctx, "PE"), "intraday", ctx.now)
    assert put["side"] == -1 and put["candidate"]["invalidation"] > put["candidate"]["trigger"]


def test_a_strike_without_recorded_bars_is_priced_from_the_brokers_quote(ctx, snap):
    far = ctx.ref.options[(MONTHLY, 25000.0, "CE")]                 # the synthetic market records the weekly only
    f = market_facts(snap, far, "expiry", ctx.now, quote={"bid": 210.0, "ask": 212.0, "ltp": 211.0, "oi": 1e6})
    assert f["contract"]["quote_source"] == "live quote" and f["contract"]["iv"]
    assert f["forward_source"].startswith("the future of the same expiry")


# ── The money ────────────────────────────────────────────────────────────────

def test_position_breakeven_and_max_loss_follow_from_the_amount(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    r = rep.build(f, rep.Params(amount=25_000), None, CAL)
    pos, ask, lot = r["position"], f["contract"]["ask"], f["contract"]["lot_size"]
    assert pos["entry"] == ask and pos["lots"] == int(25_000 // (ask * lot)) and pos["units"] == pos["shown_lots"] * lot
    assert pos["max_loss"] > pos["capital_used"]                       # premium plus charges
    assert pos["breakeven"] > f["contract"]["strike"] + ask             # premium plus charges per unit
    small = rep.build(f, rep.Params(amount=500), None, CAL)["position"]
    assert small["lots"] == 0 and small["shown_lots"] == 1 and small["min_amount"] > ask * lot


def test_the_market_view_matches_the_closed_form_chance_at_expiry(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "expiry", ctx.now)
    r = rep.build(f, rep.Params(amount=50_000, horizon="expiry"), None, CAL)
    assert r["horizon"]["settles"]
    start = datetime.fromisoformat(r["horizon"]["start"])
    t = b76.year_fraction(start, date.fromisoformat(f["contract"]["expiry"]))
    be_f = r["position"]["breakeven"] * f["forward"] / f["spot"]
    sigma = f["atm_iv"]
    d2 = (math.log(f["forward"] / be_f) - 0.5 * sigma ** 2 * t) / (sigma * math.sqrt(t))
    closed_form = b76.norm_cdf(d2)
    assert abs(r["market"]["hold"]["p_profit"] - closed_form) < 0.03


def test_under_the_markets_own_pricing_holding_loses_about_the_costs(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "expiry", ctx.now)
    r = rep.build(f, rep.Params(amount=50_000, horizon="expiry"), None, CAL)
    pos = r["position"]
    costs = pos["round_trip_charges"]
    assert -6 * costs < r["market"]["hold"]["expected"] < 2 * costs


def test_what_ifs_move_the_numbers_the_right_way(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    base = rep.build(f, rep.Params(amount=50_000), None, CAL)
    richer = rep.build(f, rep.Params(amount=50_000, iv_shift=3), None, CAL)
    slip = rep.build(f, rep.Params(amount=50_000, slippage_pct=1), None, CAL)
    assert richer["market"]["hold"]["expected"] > base["market"]["hold"]["expected"]   # IV up helps a holder
    assert slip["position"]["entry"] > base["position"]["entry"]
    assert slip["market"]["hold"]["expected"] < base["market"]["hold"]["expected"]


def test_the_plan_is_played_out_exactly_like_live_signals():
    entry, plan = 100.0, {"stop": 80.0, "t1": 130.0, "t2": 160.0}
    vals = np.array([[100, 110, 131, 150, 165],          # T1 then T2
                     [100, 95, 85, 79, 70],              # stop
                     [100, 120, 131, 126, 104],          # T1, then trails: 0.8 × 131 = 104.8 → out at 104
                     [100, 101, 99, 100, 102]], float)   # neither: out at the end
    one = rep._play(vals, entry, 0.0, plan, lots=1, lot=50, settles=False)
    assert list(one["outcome"]) == ["t2", "stop", "t1_then_stop", "time"]
    assert one["plan"][0] == 50 * (165 - 100) and one["plan"][1] == 50 * (79 - 100)
    assert one["plan"][2] == 50 * (104 - 100) and one["plan"][3] == 50 * (102 - 100)
    two = rep._play(vals[:1], entry, 0.0, plan, lots=2, lot=50, settles=False)
    assert two["plan"][0] == 50 * (131 - 100) + 50 * (165 - 100)        # half booked at T1, rest at T2


def test_scenarios_and_the_curve_cover_the_likely_range(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    r = rep.build(f, rep.Params(amount=25_000), None, CAL)
    rows = r["scenarios"]["rows"]
    assert [x["spot"] for x in rows] == sorted((x["spot"] for x in rows), reverse=True)
    assert any(x["label"] == "now" for x in rows) and {"+1σ", "−1σ"} <= {x["label"] for x in rows}
    up = next(x for x in rows if x["label"] == "+1σ")["cells"][-1]["pnl"]
    down = next(x for x in rows if x["label"] == "−1σ")["cells"][-1]["pnl"]
    assert up > 0 > down
    assert len(r["curve"]["points"]) == 61


def test_the_verdict_names_its_reasons_and_the_evidence_lists_its_assumptions(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    r = rep.build(f, rep.Params(amount=25_000), None, CAL)
    v = r["verdict"]
    assert v["call"] in ("Worth taking", "Marginal", "Avoid") and (v["for"] or v["against"])
    ev = r["evidence"]
    assert any("Black-76" in a for a in ev["assumptions"]) and any(n["label"] == "Contract IV" for n in ev["numbers"])
    assert ev["pillars"] and ev["data_times"]["source"] == "live engine"
    unpriced = rep.build({**f, "contract": {**f["contract"], "ask": None, "mid": None, "iv": None}}, rep.Params(), None, CAL)
    assert not unpriced["priced"] and unpriced["verdict"]["call"] == "Can't price"


# ── History's view ───────────────────────────────────────────────────────────

def _history_from(ctx) -> HistoryModel:
    df = ctx.state.frame(ctx.ref.spot_token, "1min")
    rows = [{"ts": ts.to_pydatetime(), "close": float(c)} for ts, c in df["close"].items()]
    return HistoryModel.from_rows(rows, before=TODAY)


def test_history_paths_line_up_with_the_simulation_times(ctx, snap):
    h = _history_from(ctx)
    assert h.sessions == 20
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    r = rep.build(f, rep.Params(amount=25_000), h, CAL)
    hist = r["history"]
    assert hist["sessions"] == 20 and 0 <= hist["hold"]["p_profit"] <= 1 and hist["similar"]["sessions"] < 30
    exp = rep.build(market_facts(snap, _atm(ctx, "CE", MONTHLY), "expiry", ctx.now,
                                 quote={"bid": 210.0, "ask": 212.0, "ltp": 211.0}), rep.Params(horizon="expiry"), h, CAL)
    assert exp["history"]["sessions"] > 0 and exp["horizon"]["settles"]


# ── The checker's own record ─────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    return Store(make_engine(f"sqlite:///{tmp_path}/c.db"))


def _bar(token, ts, close):
    return {"instrument_token": token, "ts": ts, "open": close, "high": close, "low": close, "close": close,
            "volume_day": None, "oi": None, "bid": None, "ask": None, "bid_qty": None, "ask_qty": None, "ticks": 1}


def test_outcomes_are_measured_from_saved_bars_and_build_a_record(store):
    created = ist(2026, 10, 16, 11, 0)
    check = {"id": "c1", "created_at": created, "token": 77, "expiry": WEEKLY, "strike": 25000.0, "option_right": "CE",
             "summary": {"entry": 100.0, "units": 65, "market_open": True, "horizon_end": ist(2026, 10, 16, 15, 15).isoformat(),
                         "settles": False, "spot_token": 256265, "verdict": "Worth taking", "p_profit": 0.55,
                         "capital_used": 6500.0}, "outcome": None}
    store.write_bars([_bar(77, ist(2026, 10, 16, 11, 30), 120.0), _bar(77, ist(2026, 10, 16, 15, 15), 90.0)])
    early, done = outcomes.evaluate(check, store, ist(2026, 10, 16, 12, 0))
    assert not done and early["after_30m"]["price"] == 120.0 and early["after_30m"]["pnl"] > 0
    out, done = outcomes.evaluate({**check, "outcome": early}, store, ist(2026, 10, 16, 16, 0))
    assert done and out["at_exit"]["price"] == 90.0 and out["at_exit"]["pnl"] < 0
    rec = outcomes.record([{**check, "outcome": out}])
    assert rec["verdicts"][0]["verdict"] == "Worth taking" and rec["verdicts"][0]["made_money_rate"] == 0.0
    assert rec["calibration"][0]["said"] == 0.55 and rec["calibration"][0]["happened"] == 0.0


def test_a_check_held_to_expiry_is_settled_from_niftys_close(store):
    store.write_bars([_bar(256265, ist(2026, 10, 19, 15, 29), 25080.0)])
    assert outcomes.settlement(store, 256265, WEEKLY, 25000.0, "CE") == 80.0
    assert outcomes.settlement(store, 256265, WEEKLY, 25000.0, "PE") == 0.0


# ── The recorder answers requests ────────────────────────────────────────────

def test_the_recorder_answers_a_pending_request_with_live_facts(store, ctx):
    opt = _atm(ctx, "CE")
    store.check_add({"id": "r1", "created_at": ctx.now, "username": "u", "query": "x", "index_name": "NIFTY",
                     "symbol": opt.tradingsymbol, "token": opt.token, "expiry": opt.expiry, "strike": opt.strike,
                     "option_right": opt.right, "lot_size": opt.lot_size, "status": "pending",
                     "params": {"horizon": "intraday"}, "outcome_done": 0, "paper": 0})
    watched = []
    engine = SimpleNamespace(refs={"NIFTY": ctx.ref}, context=lambda index, now: ctx, open=[])
    recorder = SimpleNamespace(watch=watched.append, wake=lambda: None)
    broker = SimpleNamespace(quotes=lambda tokens: {opt.tradingsymbol: {"bid": 99.0, "ask": 100.0, "ltp": 99.5, "oi": 1e6}})
    CheckWorker(engine, recorder, broker, store).maybe(ctx.now)
    row = store.check_get("r1")
    assert row["status"] == "facts" and row["facts"]["contract"]["ask"] == 100.0 and watched == [opt.token]
    assert not store.check_claim("r1", "pending", "offline")              # nobody answers twice


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    path = tmp_path_factory.mktemp("check") / "api.db"
    s = Store(make_engine(f"sqlite:///{path}"))
    save_market(s, build_market(), (FAR,))
    return s


@pytest.fixture
def api(saved, monkeypatch):
    evening = ist(2026, 10, 16, 18, 30)
    monkeypatch.setattr(check_routes, "now_ist", lambda: evening)
    app = FastAPI()
    app.include_router(check_routes.router)
    user = {"id": 2, "username": "viewer1", "role": "viewer", "token": "t"}
    app.dependency_overrides[check_routes.get_store] = lambda: saved
    app.dependency_overrides[check_routes.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[check_routes.get_calendar] = lambda: CAL
    app.dependency_overrides[check_routes.current_user] = lambda: user
    return TestClient(app), user


def test_resolve_endpoint_explains_typos(api):
    client, _ = api
    ok = client.get("/api/options/check/resolve", params={"q": "nifty 27 oct 25000 ce"}).json()
    assert ok["ok"] and ok["contract"]["strike"] == 25000 and ok["contract"]["expiry"] == "2026-10-27"
    bad = client.get("/api/options/check/resolve", params={"q": "nifty 27 oct 25010 ce"}).json()
    assert not bad["ok"] and "nearest" in bad["problem"] and bad["suggestions"]


def test_an_evening_check_runs_on_saved_data_then_what_if_paper_and_history(api):
    client, user = api
    r = client.post("/api/options/check", json={"query": "nifty 27 oct 25000 ce", "amount": 30000, "horizon": "expiry"})
    assert r.status_code == 200, r.text
    body = r.json()
    rep_ = body["report"]
    assert rep_["priced"] and rep_["facts"]["source"].startswith("saved data (as of Fri 16 Oct")
    assert not rep_["facts"]["market_open"] and rep_["horizon"]["starts_at_open"]
    assert rep_["horizon"]["start"].startswith("2026-10-19T09:15")             # the next open after the check
    pos = rep_["position"]
    assert pos["entry"] < rep_["facts"]["contract"]["ask"] and "time value lost" in pos["entry_note"]
    assert rep_["plan"]["entry_high"] == pos["entry"] and rep_["plan"]["stop"] < pos["entry"]
    assert rep_["verdict"]["call"] in ("Worth taking", "Marginal", "Avoid")
    check_id = body["id"]

    w = client.post(f"/api/options/check/{check_id}/whatif", json={"iv_shift": 4}).json()["report"]
    assert w["position"]["iv_used"] > rep_["position"]["iv_used"]
    again = client.get(f"/api/options/check/{check_id}").json()
    assert again["report"]["position"]["entry"] == rep_["position"]["entry"]

    paper = client.post(f"/api/options/check/{check_id}/paper").json()["paper"]
    assert paper["entry"] == rep_["position"]["entry"] and paper["exit"] is None
    closed = client.post(f"/api/options/check/{check_id}/paper/close").json()["paper"]
    assert closed["exit"] is not None and "pnl" in closed
    listing = client.get("/api/options/checks").json()
    assert listing["checks"][0]["id"] == check_id and listing["checks"][0]["summary"]["verdict"] == rep_["verdict"]["call"]
    assert "record" in listing and listing["record"]["checks"] >= 1


def test_a_typo_is_refused_with_suggestions_and_others_checks_are_private(api, saved):
    client, _ = api
    bad = client.post("/api/options/check", json={"query": "nifty 27 oct 25010 ce", "amount": 30000})
    assert bad.status_code == 422 and bad.json()["detail"]["suggestions"]
    saved.check_add({"id": "someone", "created_at": ist(2026, 10, 16, 12, 0), "username": "other", "query": "x",
                     "status": "done", "outcome_done": 0, "paper": 0})
    assert client.get("/api/options/check/someone").status_code == 404


def test_a_contract_that_expires_before_the_next_tradable_session_is_not_offered(ctx):
    refs, now = {"NIFTY": ctx.ref}, ist(2026, 10, 19, 14, 0)          # saved data from Friday: trading starts Wed
    next_open = ist(2026, 10, 21, 9, 15)
    late = resolve(parse_query("Nifty 19th Oct 25000 ce", date(2026, 10, 19)), refs, now, next_open)
    assert late.option is None and "before the next session you could trade it" in late.problem
    assert late.suggestions and late.suggestions[0].expiry == MONTHLY
    assert resolve(parse_query("25000 ce", date(2026, 10, 19)), refs, now, next_open).option.expiry == MONTHLY
    assert resolve(parse_query("25000 ce", date(2026, 10, 19)), refs, now, now).option.expiry == WEEKLY   # live session


def test_a_trade_the_engine_would_refuse_is_never_worth_taking(ctx, snap):
    f = market_facts(snap, _atm(ctx, "CE"), "intraday", ctx.now)
    strong = {**f, "score": 90, "pillars": [{**p, "status": "pass"} for p in f["pillars"]],
              "gates": [{"name": "min_rr", "ok": False, "reason": "reward:risk to T1 0.36 < 1.3"}]}
    v = rep.build(strong, rep.Params(amount=25_000), None, CAL)["verdict"]
    assert v["call"] == "Marginal" and any("wouldn't signal this" in a for a in v["against"])
    shock = {**strong, "gates": [{"name": "no_market_shock", "ok": False, "reason": "5σ move"}]}
    assert rep.build(shock, rep.Params(amount=25_000), None, CAL)["verdict"]["call"] == "Avoid"
