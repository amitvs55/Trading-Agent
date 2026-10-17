"""News pillar: RBI press releases parsed, classified by rule, and turned into an entry block."""

from datetime import timedelta

import pytest

from options.agents import news_feed
from options.agents.news_feed import NewsFetcher, NewsItem, analyse, classify, parse_rss
from options.config import OptionsSettings
from options.engine.engine import SignalEngine
from options.storage import Store, make_engine
from tests.options.fixtures import RecordingNotifier, ist
from tests.options.market import build_market
from tests.options.test_setups_engine import AlwaysBull

# The shape of https://rbi.org.in/pressreleases_rss.xml (BOM, naive IST pubDate), as fetched 17 Oct 2026
RBI_SAMPLE = """﻿<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<title>PRESS RELEASES FROM RBI</title>
<item><title>Auction of 91-Day, 182-Day and 364-Day Treasury Bills</title><pubDate>Fri, 16 Oct 2026 17:25:00</pubDate></item>
<item><title>RBI reduces the Cash Reserve Ratio by 50 basis points</title><pubDate>Fri, 16 Oct 2026 11:05:00</pubDate></item>
<item><title>Money Market Operations as on October 15, 2026</title><pubDate>Fri, 16 Oct 2026 09:00:00</pubDate></item>
<item><title>RBI announces Open Market Operation purchase of Government Securities</title><pubDate>Fri, 16 Oct 2026 10:40:00</pubDate></item>
<item><title>No date here</title></item>
</channel></rss>""".encode("utf-8")


def test_rss_is_parsed_and_classified_by_rule():
    items = parse_rss(RBI_SAMPLE, "RBI")
    assert len(items) == 4                                         # the undated item is skipped
    by = {i.title: i for i in items}
    crr = by["RBI reduces the Cash Reserve Ratio by 50 basis points"]
    assert crr.impact == "high" and crr.published == ist(2026, 10, 16, 11, 5)
    assert by["Auction of 91-Day, 182-Day and 364-Day Treasury Bills"].impact == "routine"
    assert by["Money Market Operations as on October 15, 2026"].impact == "routine"
    assert by["RBI announces Open Market Operation purchase of Government Securities"].impact == "medium"
    assert classify("Minutes of the Monetary Policy Committee Meeting") == "routine"
    assert classify("Monetary Policy Statement, 2026-27") == "high"
    assert classify("Governor's Statement") == "high"


def ctx_with(items, now, failed=()):
    ctx = build_market()
    ctx.now = now
    ctx.news = {"items": items, "failed": list(failed), "fetched_at": now}
    return ctx


def test_pillar_blocks_for_15_minutes_then_cautions():
    crr = NewsItem("RBI", "RBI reduces the Cash Reserve Ratio by 50 basis points", ist(2026, 10, 16, 11, 5), "high")
    p = analyse(ctx_with([crr], ist(2026, 10, 16, 11, 12)))
    assert p.status == "fail" and "7 min ago" in p.detail and "no new entries for 9 min" in p.detail
    assert analyse(ctx_with([crr], ist(2026, 10, 16, 11, 25))).status == "warn"      # within the hour
    assert analyse(ctx_with([crr], ist(2026, 10, 16, 12, 30))).status == "pass"
    omo = NewsItem("RBI", "OMO purchase", ist(2026, 10, 16, 11, 0), "medium")
    assert analyse(ctx_with([omo], ist(2026, 10, 16, 11, 20))).status == "warn"
    assert analyse(ctx_with([omo], ist(2026, 10, 16, 11, 45))).status == "pass"
    routine = NewsItem("RBI", "T-bill auction", ist(2026, 10, 16, 11, 0), "routine")
    assert analyse(ctx_with([routine], ist(2026, 10, 16, 11, 2))).status == "pass"
    assert analyse(ctx_with([], ist(2026, 10, 16, 11, 2), failed=["RBI"])).status == "na"
    future = NewsItem("RBI", "RBI reduces the CRR", ist(2026, 10, 16, 12, 0), "high")   # clock skew: ignored
    assert analyse(ctx_with([future], ist(2026, 10, 16, 11, 59))).status == "pass"


def test_fetcher_keeps_the_last_good_items_through_a_failed_poll():
    crr = NewsItem("RBI", "CRR cut", ist(2026, 10, 16, 11, 5), "high")
    results = iter([([crr], []), ([], ["RBI"])])
    f = NewsFetcher(fetch=lambda: next(results), now_fn=lambda: ist(2026, 10, 16, 11, 10))
    f.refresh()
    f.refresh()
    snap = f.snapshot()
    assert snap["items"] == [crr] and snap["failed"] == ["RBI"]


def test_a_fresh_high_impact_release_blocks_new_signals(tmp_path):
    ctx = build_market(trend=1)
    store = Store(make_engine(f"sqlite:///{tmp_path}/n.db"))
    shock = NewsItem("RBI", "RBI reduces the Cash Reserve Ratio by 50 basis points", ctx.now - timedelta(minutes=3), "high")
    snapshot = {"items": [shock], "failed": [], "fetched_at": ctx.now}
    eng = SignalEngine({"NIFTY": ctx.ref}, ctx.state, store, RecordingNotifier(), OptionsSettings(), ctx.calendar,
                       vix_token=ctx.vix_token, constituents={"NIFTY": ctx.constituents}, vix_history=ctx.vix_history,
                       events=[], news=lambda: snapshot, now_fn=lambda: ctx.now, setups=[AlwaysBull()])
    eng.evaluate(ctx.now)
    assert store.signals_since(ctx.now - timedelta(hours=1)) == []
    [ev] = store.evaluations_since(ctx.now - timedelta(hours=1))
    assert ev["outcome"] == "NO_TRADE" and "Cash Reserve Ratio" in ev["reasons"]


def test_feed_errors_are_reported_not_raised(monkeypatch):
    class Boom:
        def get(self, *a, **k):
            raise news_feed.requests.ConnectionError("down")
    items, failed = news_feed.fetch_feeds(Boom())
    assert items == [] and failed == ["RBI"]


# ── Shock detector (R-27) ────────────────────────────────────────────────────

def _with_bars(ctx, token, rows):
    ctx.state.add_bars([{"instrument_token": token, "ts": ts, "open": px, "high": px, "low": px, "close": px,
                         "volume_day": None, "oi": None} for ts, px in rows])


def test_a_sudden_move_blocks_entries_for_15_minutes():
    from options.agents import shock

    ctx = build_market(trend=1)
    assert not shock.analyse(ctx).active                          # an ordinary synthetic morning
    last = ctx.state.last(ctx.ref.future_token)
    t, px = last["ts"], last["close"]
    _with_bars(ctx, ctx.ref.future_token, [(t + timedelta(minutes=1), px * 0.985)])   # −1.5% in a minute
    ctx.now = t + timedelta(minutes=2, seconds=3)
    v = shock.analyse(ctx)
    assert v.active and "one minute" in v.detail and v.until == t + timedelta(minutes=17)
    ctx.now = t + timedelta(minutes=30)
    _with_bars(ctx, ctx.ref.future_token, [(t + timedelta(minutes=m), px * 0.985) for m in range(2, 30)])
    assert not shock.analyse(ctx).active                          # quiet again: the block lapses


def test_a_vix_jump_is_a_shock():
    from options.agents import shock

    ctx = build_market(trend=1)
    t = ctx.state.last(ctx.vix_token)["ts"]
    _with_bars(ctx, ctx.vix_token, [(t + timedelta(minutes=m), 13.0 * (1 + 0.012 * m)) for m in range(1, 11)])
    ctx.now = t + timedelta(minutes=11)
    v = shock.analyse(ctx)
    assert v.active and "India VIX" in v.detail
