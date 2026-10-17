"""Tests for token usage tracking and USD cost calculation."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.settings import settings
from utils import usage as usage_mod
from utils.usage import UsageTracker, compute_cost, resolve_price


@pytest.fixture(autouse=True)
def no_price_overrides(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_PRICE_INPUT_PER_1M", None)
    monkeypatch.setattr(settings, "OPENAI_PRICE_OUTPUT_PER_1M", None)


@pytest.fixture
def fixed_pricing(monkeypatch):
    """Known prices so the math checks don't depend on the real table."""
    monkeypatch.setattr(usage_mod, "PRICING", {
        "test-model": (2.00, 8.00, 0.50),
        "test-model-mini": (0.40, 1.60, None),
    })


# ─── Cost math ───────────────────────────────────────────────────────────────


def test_cost_prompt_and_completion(fixed_pricing):
    # 1M input at $2 + 500k output at $8 = $2 + $4
    assert compute_cost("test-model", 1_000_000, 500_000) == pytest.approx(6.0)


def test_cost_cached_tokens_use_cached_rate(fixed_pricing):
    # 1M prompt of which 400k cached: 600k * $2 + 400k * $0.50 = $1.20 + $0.20
    assert compute_cost("test-model", 1_000_000, 0, cached_tokens=400_000) == pytest.approx(1.4)


def test_cost_cached_tokens_without_cached_rate_bill_at_input(fixed_pricing):
    assert compute_cost("test-model-mini", 1_000_000, 0, cached_tokens=400_000) == pytest.approx(0.40)


def test_small_call_cost(fixed_pricing):
    # 1,200 in + 300 out = 0.0024 + 0.0024
    assert compute_cost("test-model", 1200, 300) == pytest.approx(0.0048)


# ─── Model matching ──────────────────────────────────────────────────────────


def test_longest_prefix_wins(fixed_pricing):
    assert resolve_price("test-model-mini-2024-07-18").input_per_1m == 0.40
    assert resolve_price("test-model-2025-01-01").input_per_1m == 2.00


def test_real_table_snapshots_resolve():
    assert resolve_price("gpt-4o-mini-2024-07-18") == resolve_price("gpt-4o-mini")
    assert resolve_price("gpt-4o-2024-08-06") == resolve_price("gpt-4o")
    assert resolve_price("gpt-4-0613") == resolve_price("gpt-4")
    assert resolve_price("gpt-4o-mini").input_per_1m < resolve_price("gpt-4o").input_per_1m


def test_unknown_model_is_free_and_flagged(fixed_pricing):
    price = resolve_price("some-local-llama")
    assert price.known is False
    assert compute_cost("some-local-llama", 10_000, 10_000) == 0.0
    tracker = UsageTracker("some-local-llama")
    assert tracker.summary()["pricing_known"] is False


# ─── Env overrides ───────────────────────────────────────────────────────────


def test_env_override_takes_precedence(fixed_pricing, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_PRICE_INPUT_PER_1M", 1.0)
    monkeypatch.setattr(settings, "OPENAI_PRICE_OUTPUT_PER_1M", 3.0)
    assert compute_cost("test-model", 1_000_000, 1_000_000) == pytest.approx(4.0)
    # Cached tokens bill at the overridden input rate
    assert compute_cost("test-model", 1_000_000, 0, cached_tokens=500_000) == pytest.approx(1.0)


def test_env_override_makes_unknown_model_known(fixed_pricing, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_PRICE_INPUT_PER_1M", 1.0)
    monkeypatch.setattr(settings, "OPENAI_PRICE_OUTPUT_PER_1M", 2.0)
    price = resolve_price("some-local-llama")
    assert price.known is True
    assert compute_cost("some-local-llama", 1_000_000, 1_000_000) == pytest.approx(3.0)


# ─── Tracker ─────────────────────────────────────────────────────────────────


def test_summary_breakdowns(fixed_pricing):
    t = UsageTracker("test-model")
    t.stage = 1
    t.record("news_analyst", "test-model", 1000, 200)
    t.record("news_analyst", "test-model", 1000, 200, is_retry=True)
    t.stage = 3
    t.record("trader", "test-model", 500, 100)

    s = t.summary()
    assert s["calls"] == 3
    assert s["total_tokens"] == 3000
    assert s["retries"] == 1
    assert s["by_agent"]["news_analyst"]["calls"] == 2
    assert s["by_stage"]["1"]["total_tokens"] == 2400
    assert s["by_stage"]["3"]["total_tokens"] == 600
    assert s["cost_usd"] == pytest.approx(sum(c["cost_usd"] for c in s["calls_detail"]))
    json.dumps(s)  # must be JSON-safe for SSE and the trade log


def test_tracker_thread_safety(fixed_pricing):
    t = UsageTracker("test-model")
    per_thread = 250
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        for _ in range(per_thread):
            t.record(f"agent_{i}", "test-model", 100, 50)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    s = t.summary()
    assert s["calls"] == 8 * per_thread
    assert s["prompt_tokens"] == 8 * per_thread * 100
    assert s["completion_tokens"] == 8 * per_thread * 50
    assert all(b["calls"] == per_thread for b in s["by_agent"].values())
    assert s["cost_usd"] == pytest.approx(8 * per_thread * compute_cost("test-model", 100, 50), rel=1e-4)


# ─── LLMClient integration (mocked OpenAI) ───────────────────────────────────


def _fake_response(prompt, completion, cached=0, model="test-model-2025-01-01"):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
    )


def test_llm_client_records_usage(fixed_pricing, monkeypatch):
    from utils.llm import LLMClient

    monkeypatch.setattr(settings, "MODEL_NAME", "test-model")
    client = LLMClient(agent_name="trader")
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = _fake_response(2000, 500, cached=1000)
    client.tracker = UsageTracker("test-model")
    client.tracker.stage = 3

    assert client.call("sys", "user") == {"ok": True}
    client.call("sys", "user again", is_retry=True)

    s = client.tracker.summary()
    assert s["calls"] == 2
    assert s["cached_tokens"] == 2000
    assert s["retries"] == 1
    assert s["by_agent"]["trader"]["total_tokens"] == 5000
    assert s["by_stage"]["3"]["calls"] == 2
    expected = compute_cost("test-model", 2000, 500, cached_tokens=1000) * 2
    assert s["cost_usd"] == pytest.approx(expected)


def test_llm_client_without_tracker_still_works(monkeypatch):
    from utils.llm import LLMClient

    client = LLMClient()
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = _fake_response(10, 5)
    assert client.call("sys", "user") == {"ok": True}


# ─── /api/usage aggregation ──────────────────────────────────────────────────


def test_usage_route_handles_empty_and_old_records(tmp_path):
    from datetime import datetime, timezone

    from api.routes import usage as route
    from options.core.calendar import now_ist
    from options.storage import Store, make_engine

    store = Store(make_engine(f"sqlite:///{tmp_path}/u.db"))

    # No runs yet
    empty = route.get_usage(store)
    assert empty["all_time"]["runs"] == 0
    assert len(empty["daily"]) == 30
    assert empty["most_expensive_agent"] is None

    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.research_start("old", "OLD.NS", "NSE", None, "m", old)
    store.research_finish("old", old, status="done", order_status="held")           # before usage tracking
    usage = {"model": "gpt-4o-mini", "calls": 3, "prompt_tokens": 3000, "completion_tokens": 600,
             "cached_tokens": 0, "total_tokens": 3600, "cost_usd": 0.0012,
             "by_agent": {"trader": {"calls": 1, "total_tokens": 1000, "cost_usd": 0.0002},
                          "news_analyst": {"calls": 2, "total_tokens": 2600, "cost_usd": 0.0010}}}
    store.research_start("new", "NEW.NS", "NSE", None, "m", now_ist())
    store.research_finish("new", now_ist(), status="done", order_status="held", usage=json.dumps(usage),
                          cost_usd=0.0012)

    data = route.get_usage(store)
    assert data["untracked_runs"] == 1
    assert data["all_time"]["runs"] == 1
    assert data["today"]["cost_usd"] == pytest.approx(0.0012)
    assert data["last_7_days"]["total_tokens"] == 3600
    assert data["daily"][-1]["cost_usd"] == pytest.approx(0.0012)
    assert data["most_expensive_agent"]["agent"] == "news_analyst"
