"""How confident a signal is, in words a trader can check (plan §5 scoring, made readable).

The score is the confluence score from grading: each of ten pillars is worth a fixed number of
points (weights add to 100) and earns all of them on a pass, half on a warn or n/a, none on a
fail. It measures how much of the analysis agrees, not a probability of winning. That only
comes from the track record, so `band` adds the real results of the same grade once there are
enough of them to mean something.
"""

from options.core.schemas import Signal
from options.engine import performance
from options.engine.grading import GRADE_A, GRADE_B, PILLAR_WEIGHTS, STATUS_POINTS

LABELS = {"trend": "Trend", "futures_flow": "Futures flow", "option_chain": "Option chain", "trigger": "Trigger",
          "levels": "Key levels", "volatility": "Volatility", "breadth": "Breadth", "momentum": "Momentum",
          "macro": "Global markets", "timing": "Timing"}
MIN_TRADES = 20                     # below this, a win rate is mostly noise


def level(score: float) -> str:
    if score >= 85:
        return "Very high"
    if score >= GRADE_A:
        return "High"
    if score >= GRADE_B:
        return "Moderate"
    return "Low"


def breakdown(sig: Signal) -> dict:
    checks = {c.pillar: c for c in sig.checks}
    parts = []
    for pillar, weight in PILLAR_WEIGHTS.items():
        check = checks.get(pillar)
        status = check.status if check else "na"
        parts.append({"pillar": pillar, "label": LABELS.get(pillar, pillar), "weight": weight,
                      "points": round(weight * STATUS_POINTS[status], 1), "status": status,
                      "detail": check.detail if check else "not checked"})
    strengths = [p["label"] for p in sorted(parts, key=lambda p: -p["weight"]) if p["status"] == "pass"][:3]
    lost = sorted((p for p in parts if p["points"] < p["weight"]), key=lambda p: p["points"] - p["weight"])
    return {
        "score": round(sig.score, 1),
        "max": 100,
        "grade": sig.grade.value,
        "level": level(sig.score),
        "parts": parts,
        "strengths": strengths,
        "weaknesses": [{"label": p["label"], "lost": round(p["weight"] - p["points"], 1), "detail": p["detail"]}
                       for p in lost[:3]],
    }


def band_stats(signals: list[Signal]) -> dict[str, dict]:
    """Real results per grade, for 'what happened to signals like this one'."""
    out = {}
    for grade, st in performance.by(signals, "grade").items():
        out[grade] = {"grade": grade, "label": f"Grade {grade} ({GRADE_A}+)" if grade == "A" else
                      f"Grade {grade} ({GRADE_B}–{GRADE_A - 1})" if grade == "B" else f"Grade {grade}",
                      "trades": st["trades"], "win_rate": st["win_rate"], "avg_r": st["avg_r"],
                      "enough": st["trades"] >= MIN_TRADES, "min_trades": MIN_TRADES}
    return out


def with_band(conf: dict, bands: dict[str, dict]) -> dict:
    band = bands.get(conf["grade"]) or {"grade": conf["grade"], "trades": 0, "win_rate": None, "avg_r": None,
                                        "enough": False, "min_trades": MIN_TRADES}
    return {**conf, "band": band}


def telegram_line(sig: Signal, band: dict | None = None) -> str:
    conf = breakdown(sig)
    weak = ", ".join(f"{w['label'].lower()} −{w['lost']:g}" for w in conf["weaknesses"][:2]) or "none"
    line = f"Confidence {conf['score']:.0f}/100 ({conf['level'].lower()}) · lost points: {weak}"
    if band and band.get("enough"):
        line += f" · grade {band['grade']} so far: {band['win_rate'] * 100:.0f}% won over {band['trades']}"
    return line
