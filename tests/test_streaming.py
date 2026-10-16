"""Tests for SSE serialization."""

import json
import math

from api.streaming_pipeline import _serialize
from models.schemas import FundamentalsOutput


def test_serialize_replaces_nan_and_inf_with_null():
    model = FundamentalsOutput(
        agent_name="fundamentals_analyst", ticker="RELIANCE.NS",
        pe_ratio=math.nan, forward_pe=math.inf, health_score="moderate", summary="x",
    )
    out = _serialize({"fundamentals": model, "vals": [1.5, -math.inf]})
    assert out["fundamentals"]["pe_ratio"] is None
    assert out["fundamentals"]["forward_pe"] is None
    assert out["vals"] == [1.5, None]
    # Must be strict JSON — the browser's JSON.parse rejects NaN
    json.dumps(out, allow_nan=False)
