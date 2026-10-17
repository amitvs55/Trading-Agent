"""Shock detector (roadmap R-27): no new entries right after the market lurches.

Scheduled events and RBI releases are handled elsewhere; this catches the moves nobody announced.
A shock is either
- a one-minute move in the near-month future of SIGMA_LIMIT or more standard deviations, measured
  against the hour of one-minute moves before it (same session only, so the opening gap never counts), or
- India VIX up VIX_JUMP or more within 15 minutes.
New entries are blocked for BLOCK_FOR after the shock; open signals keep their exits.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from options.agents.context import AgentContext

SIGMA_LIMIT = 5.0
VIX_JUMP = 0.10
BLOCK_FOR = timedelta(minutes=15)
BASELINE = 60            # one-minute moves the spread is measured over
MIN_BASELINE = 30


@dataclass(frozen=True)
class ShockView:
    active: bool
    detail: str
    until: datetime | None = None


def analyse(ctx: AgentContext) -> ShockView:
    now = ctx.now
    f = ctx.state.frame(ctx.ref.future_token, "1min")
    if len(f) > MIN_BASELINE + 1:
        today = f[f.index.date == now.date()]
        rets = np.log(today["close"]).diff().dropna()           # within today's session only
        recent = rets[rets.index > now - BLOCK_FOR]
        base = rets[rets.index <= now - BLOCK_FOR].iloc[-BASELINE:]
        if len(base) >= MIN_BASELINE and len(recent) and base.std() > 0:
            z = recent / base.std()
            big = z[z.abs() >= SIGMA_LIMIT]
            if len(big):
                at = big.index[-1].to_pydatetime()
                move = float(np.expm1(recent.loc[big.index[-1]]) * 100)
                until = at + timedelta(minutes=1) + BLOCK_FOR
                return ShockView(True, f"market shock: NIFTY future {move:+.2f}% in one minute ({abs(float(big.iloc[-1])):.1f}σ) "
                                       f"at {at:%H:%M}; no new entries until {until:%H:%M}", until)
    if ctx.vix_token:
        v = ctx.state.frame(ctx.vix_token, "1min")
        v = v[v.index.date == now.date()] if len(v) else v
        if len(v) >= 2:
            then = v[v.index <= now - BLOCK_FOR]
            start = float(then["close"].iloc[-1]) if len(then) else float(v["close"].iloc[0])
            last = float(v["close"].iloc[-1])
            if start > 0 and last / start - 1 >= VIX_JUMP:
                return ShockView(True, f"market shock: India VIX {start:.1f} → {last:.1f} "
                                       f"(+{(last / start - 1) * 100:.0f}%) within 15 min; no new entries for now")
    return ShockView(False, "no shock")
