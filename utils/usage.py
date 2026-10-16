"""OpenAI token usage tracking and USD cost estimation."""

import threading
from dataclasses import asdict, dataclass
from typing import Any

from config.settings import settings

# USD per 1M tokens: (input, output, cached_input or None).
# Prices change — verify against https://openai.com/api/pricing before trusting totals.
# Override per deployment with OPENAI_PRICE_INPUT_PER_1M / OPENAI_PRICE_OUTPUT_PER_1M.
PRICING: dict[str, tuple[float, float, float | None]] = {
    "gpt-5":               (1.25, 10.00, 0.125),
    "gpt-5-mini":          (0.25, 2.00, 0.025),
    "gpt-5-nano":          (0.05, 0.40, 0.005),
    "gpt-4.1":             (2.00, 8.00, 0.50),
    "gpt-4.1-mini":        (0.40, 1.60, 0.10),
    "gpt-4.1-nano":        (0.10, 0.40, 0.025),
    "gpt-4o":              (2.50, 10.00, 1.25),
    "gpt-4o-2024-05-13":   (5.00, 15.00, None),
    "gpt-4o-mini":         (0.15, 0.60, 0.075),
    "gpt-4-turbo":         (10.00, 30.00, None),
    "gpt-4-1106-preview":  (10.00, 30.00, None),
    "gpt-4-0125-preview":  (10.00, 30.00, None),
    "gpt-4":               (30.00, 60.00, None),
    "gpt-4-32k":           (60.00, 120.00, None),
    "gpt-3.5-turbo":       (0.50, 1.50, None),
    "o1":                  (15.00, 60.00, 7.50),
    "o1-mini":             (1.10, 4.40, 0.55),
    "o3":                  (2.00, 8.00, 0.50),
    "o3-mini":             (1.10, 4.40, 0.55),
    "o4-mini":             (1.10, 4.40, 0.275),
}


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None
    known: bool


def resolve_price(model: str) -> ModelPrice:
    """Find the price for a model by longest matching prefix, applying env overrides."""
    name = model.lower()
    match = max((k for k in PRICING if name.startswith(k)), key=len, default=None)
    inp, out, cached = PRICING[match] if match else (0.0, 0.0, None)
    known = match is not None

    in_override = settings.OPENAI_PRICE_INPUT_PER_1M
    out_override = settings.OPENAI_PRICE_OUTPUT_PER_1M
    if in_override is not None:
        # The table's cached rate belongs to the table's input rate, so drop it
        inp, cached = in_override, None
    if out_override is not None:
        out = out_override
    if in_override is not None and out_override is not None:
        known = True

    return ModelPrice(inp, out, cached, known)


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    """USD cost of one call. prompt_tokens includes cached_tokens, as in the OpenAI usage object."""
    price = resolve_price(model)
    cached = min(cached_tokens, prompt_tokens)
    cached_rate = price.cached_input_per_1m if price.cached_input_per_1m is not None else price.input_per_1m
    return (
        (prompt_tokens - cached) * price.input_per_1m
        + cached * cached_rate
        + completion_tokens * price.output_per_1m
    ) / 1_000_000


@dataclass
class UsageRecord:
    agent: str
    stage: int | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost_usd: float
    latency_s: float
    is_retry: bool


def _empty_bucket() -> dict[str, Any]:
    return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "cached_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}


def _add(bucket: dict[str, Any], r: UsageRecord) -> None:
    bucket["calls"] += 1
    bucket["prompt_tokens"] += r.prompt_tokens
    bucket["completion_tokens"] += r.completion_tokens
    bucket["cached_tokens"] += r.cached_tokens
    bucket["total_tokens"] += r.total_tokens
    bucket["cost_usd"] += r.cost_usd


class UsageTracker:
    """Collects LLM usage for one pipeline run. Safe to record from many threads."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.MODEL_NAME
        self.stage: int | None = None
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()

    def record(
        self,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        latency_s: float = 0.0,
        is_retry: bool = False,
        stage: int | None = None,
    ) -> UsageRecord:
        rec = UsageRecord(
            agent=agent,
            stage=stage if stage is not None else self.stage,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=compute_cost(model, prompt_tokens, completion_tokens, cached_tokens),
            latency_s=round(latency_s, 2),
            is_retry=is_retry,
        )
        with self._lock:
            self._records.append(rec)
        return rec

    def summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)

        totals = _empty_bucket()
        by_agent: dict[str, dict[str, Any]] = {}
        by_stage: dict[str, dict[str, Any]] = {}
        for r in records:
            _add(totals, r)
            _add(by_agent.setdefault(r.agent, _empty_bucket()), r)
            _add(by_stage.setdefault(str(r.stage) if r.stage is not None else "unknown", _empty_bucket()), r)

        price = resolve_price(self.model)
        return {
            "model": self.model,
            "pricing_known": price.known,
            "input_price_per_1m": price.input_per_1m,
            "output_price_per_1m": price.output_per_1m,
            **{k: (round(v, 6) if k == "cost_usd" else v) for k, v in totals.items()},
            "retries": sum(1 for r in records if r.is_retry),
            "by_agent": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_agent.items()},
            "by_stage": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_stage.items()},
            "calls_detail": [asdict(r) for r in records],
        }
