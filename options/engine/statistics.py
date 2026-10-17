"""Is the track record real, or noise? (review findings F-01, F-13; roadmap R-16, R-17)

Point estimates (win rate, average R) say nothing about how sure we are. This module adds:
- a 95% confidence interval and t-statistic for the average R per trade, and how many more trades
  the current results need before a positive expectancy is statistically meaningful;
- Sharpe and Sortino ratios on daily P&L, annualised;
- the Probabilistic and Deflated Sharpe Ratios (Bailey & López de Prado), which discount a good
  result for being the best of several setups tried;
- calibration: do higher confidence scores and passed pillars actually win more?

Pure functions over signals; standard library only (statistics.NormalDist, no SciPy).
"""

from collections import defaultdict
from datetime import date
from math import ceil, e, sqrt
from statistics import NormalDist, fmean, stdev

from options.core.schemas import Signal, SignalState

NORMAL = NormalDist()
EULER_GAMMA = 0.5772156649
MIN_TRADES = 20            # below this, intervals are reported but flagged as too few
TRADING_DAYS = 252


def t_quantile(p: float, df: int) -> float:
    """Student's t quantile (Abramowitz & Stegun 26.7.5): within 0.001 of exact for df ≥ 3."""
    z = NORMAL.inv_cdf(p)
    if df >= 1000:
        return z
    g1 = (z ** 3 + z) / 4
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384
    g4 = (79 * z ** 9 + 776 * z ** 7 + 1482 * z ** 5 - 1920 * z ** 3 - 945 * z) / 92160
    return z + g1 / df + g2 / df ** 2 + g3 / df ** 3 + g4 / df ** 4


def mean_interval(values: list[float], conf: float = 0.95) -> tuple[float, float] | None:
    n = len(values)
    if n < 2:
        return None
    m, s = fmean(values), stdev(values)
    half = t_quantile(0.5 + conf / 2, n - 1) * s / sqrt(n)
    return m - half, m + half


def trades_needed(values: list[float], conf: float = 0.95) -> int | None:
    """More trades needed before the one-sided lower bound of the mean clears zero, at today's mean
    and spread. None when the mean isn't positive (no number of trades would prove an edge)."""
    n = len(values)
    if n < 2:
        return None
    m, s = fmean(values), stdev(values)
    if m <= 0:
        return None
    if s == 0:
        return 0
    req = n
    for _ in range(20):                                   # t depends on n: iterate to a fixed point
        new = ceil((t_quantile(conf, max(req - 1, 1)) * s / m) ** 2)
        if new == req:
            break
        req = new
    return max(0, req - n)


def _moments(values: list[float]) -> tuple[float, float]:
    """Sample skewness and (non-excess) kurtosis."""
    n, m = len(values), fmean(values)
    s = stdev(values)
    if s == 0:
        return 0.0, 3.0
    skew = sum((v - m) ** 3 for v in values) / n / s ** 3
    kurt = sum((v - m) ** 4 for v in values) / n / s ** 4
    return skew, kurt


def probabilistic_sharpe(values: list[float], benchmark_sr: float = 0.0) -> float | None:
    """P(true per-trade Sharpe > benchmark_sr), allowing for skew and fat tails."""
    n = len(values)
    if n < 3 or stdev(values) == 0:
        return None
    sr = fmean(values) / stdev(values)
    skew, kurt = _moments(values)
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return None
    return NORMAL.cdf((sr - benchmark_sr) * sqrt(n - 1) / sqrt(denom))


def deflated_sharpe(values: list[float], trial_srs: list[float]) -> float | None:
    """The PSR against the Sharpe the best of N independent tries would reach by luck alone."""
    trials = [s for s in trial_srs if s == s]
    if len(trials) < 2:
        return probabilistic_sharpe(values, 0.0)
    n = len(trials)
    spread = stdev(trials)
    expected_max = spread * ((1 - EULER_GAMMA) * NORMAL.inv_cdf(1 - 1 / n) + EULER_GAMMA * NORMAL.inv_cdf(1 - 1 / (n * e)))
    return probabilistic_sharpe(values, expected_max)


def daily_returns(signals: list[Signal], capital: float, trading_days: list[date]) -> list[float]:
    """Each trading day's net P&L as a share of capital, zero on days without a closed trade."""
    by_day: dict[date, float] = defaultdict(float)
    for s in signals:
        if s.state is SignalState.CLOSED and s.pnl_rupees is not None and s.closed_at:
            by_day[s.closed_at.date()] += s.pnl_rupees
    return [by_day.get(d, 0.0) / capital for d in trading_days]


def sharpe_sortino(returns: list[float]) -> tuple[float | None, float | None]:
    if len(returns) < 5:
        return None, None
    m = fmean(returns)
    sd = stdev(returns)
    downside = sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
    sharpe = m / sd * sqrt(TRADING_DAYS) if sd > 0 else None
    sortino = m / downside * sqrt(TRADING_DAYS) if downside > 0 else None
    return sharpe, sortino


def _traded(signals: list[Signal]) -> list[Signal]:
    return sorted((s for s in signals if s.state is SignalState.CLOSED and s.r_multiple is not None),
                  key=lambda s: s.closed_at)


def record_stats(signals: list[Signal], trial_srs: list[float] | None = None) -> dict:
    """Uncertainty around a set of trades, in R multiples (comparable across lot sizes)."""
    rs = [s.r_multiple for s in _traded(signals)]
    n = len(rs)
    out = {"trades": n, "enough": n >= MIN_TRADES, "min_trades": MIN_TRADES, "mean_r": None, "sd_r": None,
           "ci_r": None, "t_stat": None, "significant": False, "trades_needed": None, "sharpe_per_trade": None,
           "psr": None, "dsr": None}
    if n == 0:
        return out
    out["mean_r"] = fmean(rs)
    if n >= 2:
        sd = stdev(rs)
        out["sd_r"] = sd
        ci = mean_interval(rs)
        out["ci_r"] = list(ci) if ci else None
        out["t_stat"] = fmean(rs) / (sd / sqrt(n)) if sd > 0 else None
        out["significant"] = bool(ci and ci[0] > 0)
        out["trades_needed"] = trades_needed(rs)
        out["sharpe_per_trade"] = fmean(rs) / sd if sd > 0 else None
        out["psr"] = probabilistic_sharpe(rs)
        out["dsr"] = deflated_sharpe(rs, trial_srs) if trial_srs is not None else out["psr"]
    return out


def setup_report(signals: list[Signal]) -> dict:
    """Per-setup uncertainty, with each setup's Sharpe deflated for the number of setups tried."""
    groups: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        groups[s.setup].append(s)
    trial_srs = []
    for group in groups.values():
        rs = [s.r_multiple for s in _traded(group)]
        if len(rs) >= 2 and stdev(rs) > 0:
            trial_srs.append(fmean(rs) / stdev(rs))
    return {k: record_stats(v, trial_srs) for k, v in sorted(groups.items())}


def account_stats(signals: list[Signal], capital: float, trading_days: list[date]) -> dict:
    """Risk-adjusted returns on the capital, over every trading day of the record."""
    done = _traded(signals)
    total = sum(s.pnl_rupees or 0 for s in done)
    rets = daily_returns(done, capital, trading_days)
    sharpe, sortino = sharpe_sortino(rets)
    days = len(trading_days)
    ret = total / capital if capital else 0.0
    annual = ((1 + ret) ** (TRADING_DAYS / days) - 1) if days >= 20 and ret > -1 else None
    return {"days": days, "return_pct": ret * 100, "annualised_pct": annual * 100 if annual is not None else None,
            "sharpe": sharpe, "sortino": sortino}


def calibration(signals: list[Signal]) -> dict:
    """Do higher scores, and pillars that passed, go with better results?"""
    done = _traded(signals)

    def summary(group: list[Signal]) -> dict:
        rs = [s.r_multiple for s in group]
        return {"trades": len(group), "win_rate": sum(r > 0 for r in rs) / len(rs) if rs else None,
                "avg_r": fmean(rs) if rs else None}

    bands = [(60, 70), (70, 80), (80, 90), (90, 101)]
    by_band = [{"band": f"{lo}–{min(hi, 100) if hi < 101 else 100}", **summary([s for s in done if lo <= s.score < hi])}
               for lo, hi in bands]
    filled = [b for b in by_band if b["trades"] >= 5]
    monotonic = (all(a["avg_r"] <= b["avg_r"] for a, b in zip(filled, filled[1:])) if len(filled) >= 2 else None)

    pillars: dict[str, dict[str, list[Signal]]] = defaultdict(lambda: defaultdict(list))
    for s in done:
        for c in s.checks:
            pillars[c.pillar][c.status].append(s)
    by_pillar = {}
    for pillar, statuses in sorted(pillars.items()):
        rows = {st: summary(group) for st, group in statuses.items()}
        passed, other = rows.get("pass"), [g for st, g in statuses.items() if st != "pass"]
        rest = summary([s for g in other for s in g])
        lift = (passed["avg_r"] - rest["avg_r"]
                if passed and passed["avg_r"] is not None and rest["avg_r"] is not None else None)
        by_pillar[pillar] = {"by_status": rows, "lift_r": lift}
    return {"trades": len(done), "enough": len(done) >= MIN_TRADES, "by_score": by_band,
            "score_monotonic": monotonic, "by_pillar": by_pillar}
