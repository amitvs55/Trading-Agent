"""Global & macro agent (pillar 10): risk-on/off context from world markets.

yfinance quotes are delayed, which is fine for context (weight 5 of 100) and never used
for a trigger. GIFT Nifty is not available through Kite or yfinance, so the morning gap
estimate uses Asian and US futures instead.
"""

import threading
from datetime import datetime, timedelta
from typing import Callable

from options.agents.context import AgentContext
from options.core.calendar import now_ist
from options.core.schemas import PillarView
from utils.logger import setup_logger

logger = setup_logger("options.macro")

# name → (yfinance symbol, sign: +1 if a rise is risk-on for Indian equities)
MACRO_SYMBOLS: dict[str, tuple[str, int]] = {
    "S&P 500 fut": ("ES=F", 1),
    "Nasdaq fut": ("NQ=F", 1),
    "Nikkei": ("^N225", 1),
    "Hang Seng": ("^HSI", 1),
    "USD/INR": ("INR=X", -1),
    "Brent": ("BZ=F", -1),
    "US 10Y": ("^TNX", -1),
}


def yfinance_changes() -> dict[str, float]:
    """% change of each symbol's last price vs its previous daily close."""
    import yfinance as yf

    out = {}
    for name, (symbol, _) in MACRO_SYMBOLS.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d", interval="1d")["Close"].dropna()
            if len(hist) >= 2:
                out[name] = float((hist.iloc[-1] / hist.iloc[-2] - 1) * 100)
        except Exception as e:
            logger.warning("macro fetch failed for %s: %s", symbol, type(e).__name__)
    return out


class MacroFetcher:
    """Refreshes global changes in a background thread every `every_s` seconds."""

    def __init__(self, fetch: Callable[[], dict[str, float]] = yfinance_changes, every_s: int = 900,
                 now_fn: Callable[[], datetime] = now_ist):
        self._fetch, self._every, self._now = fetch, every_s, now_fn
        self._lock = threading.Lock()
        self._snap: dict | None = None
        self._stop = threading.Event()

    def refresh(self) -> None:
        try:
            changes = self._fetch()
        except Exception as e:
            logger.warning("macro refresh failed: %s", type(e).__name__)
            return
        if changes:
            with self._lock:
                self._snap = {"changes": changes, "fetched_at": self._now()}

    def snapshot(self) -> dict | None:
        with self._lock:
            return dict(self._snap) if self._snap else None

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self._every)
        threading.Thread(target=loop, name="macro", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def analyse(ctx: AgentContext) -> PillarView:
    snap = ctx.macro
    if not snap or not snap.get("changes"):
        return PillarView("macro", "No global market data", status="na")
    changes = snap["changes"]
    parts = [(MACRO_SYMBOLS[n][1] * max(-1.0, min(1.0, chg)), n, chg) for n, chg in changes.items() if n in MACRO_SYMBOLS]
    score = sum(p for p, _, _ in parts) / len(parts)
    stale = ctx.now - snap["fetched_at"] > timedelta(hours=2)
    strength = min(1.0, abs(score) * 1.5) * (0.5 if stale else 1.0)
    detail = ", ".join(f"{n} {c:+.1f}%" for _, n, c in sorted(parts, key=lambda p: -abs(p[2]))[:4])
    if stale:
        detail += " (stale)"
    return PillarView("macro", detail, bias=(1 if score > 0.15 else -1 if score < -0.15 else 0),
                      strength=strength, features={"risk_score": score, **changes})
