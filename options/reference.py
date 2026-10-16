"""Contract reference data built from the Kite instrument dump each morning.

Expiries, lot sizes and strike steps are never hard-coded (plan §2): NSE changes them, and
the instrument dump already carries holiday-adjusted expiry dates.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

# Kite tradingsymbols of the underlying indices (segment "INDICES" on NSE)
INDEX_SPOT_SYMBOLS = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE"}
VIX_SYMBOL = "INDIA VIX"


def as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass(frozen=True)
class OptionInfo:
    token: int
    tradingsymbol: str
    expiry: date
    strike: float
    right: str          # "CE" | "PE"
    lot_size: int


@dataclass
class IndexReference:
    index: str
    spot_token: int
    future_token: int
    future_symbol: str
    future_expiry: date
    expiries: list[date]                 # option expiries on or after today, nearest first
    lot_size: int
    strike_step: float
    options: dict[tuple[date, float, str], OptionInfo] = field(repr=False)

    def strikes(self, expiry: date) -> list[float]:
        return sorted({strike for exp, strike, _ in self.options if exp == expiry})

    def atm_strike(self, price: float, expiry: date | None = None) -> float:
        return min(self.strikes(expiry or self.expiries[0]), key=lambda s: abs(s - price))

    def window(self, price: float, width: int, n_expiries: int) -> list[OptionInfo]:
        """CE and PE contracts for `width` listed strikes either side of ATM, nearest expiries."""
        out: list[OptionInfo] = []
        for exp in self.expiries[:n_expiries]:
            strikes = self.strikes(exp)
            i = strikes.index(min(strikes, key=lambda s: abs(s - price)))
            for strike in strikes[max(0, i - width): i + width + 1]:
                for right in ("CE", "PE"):
                    opt = self.options.get((exp, strike, right))
                    if opt:
                        out.append(opt)
        return out


def find_token(nse_rows: list[dict], tradingsymbol: str) -> int:
    for r in nse_rows:
        if r["tradingsymbol"] == tradingsymbol and r.get("segment") == "INDICES":
            return int(r["instrument_token"])
    raise LookupError(f"{tradingsymbol!r} not found in the NSE instrument dump")


def infer_strike_step(strikes: list[float], around: float, band_pct: float = 0.05) -> float:
    """Most common gap between listed strikes within ±band_pct of `around` (far strikes are wider)."""
    near = sorted(s for s in set(strikes) if abs(s - around) <= around * band_pct)
    diffs = [round(b - a, 2) for a, b in zip(near, near[1:])]
    if not diffs:
        raise ValueError(f"not enough strikes near {around} to infer the strike step")
    return Counter(diffs).most_common(1)[0][0]


def index_rows(nfo_rows: list[dict], index: str, today: date) -> list[dict]:
    """Live (unexpired) futures and options rows of one index."""
    return [r for r in nfo_rows
            if r.get("name") == index and r.get("segment") in ("NFO-FUT", "NFO-OPT")
            and (as_date(r.get("expiry")) or date.min) >= today]


def build_reference(index: str, nse_rows: list[dict], nfo_rows: list[dict], today: date,
                    spot_price: float | None = None) -> IndexReference:
    spot_token = find_token(nse_rows, INDEX_SPOT_SYMBOLS[index])
    rows = index_rows(nfo_rows, index, today)

    futures = sorted((r for r in rows if r["segment"] == "NFO-FUT"), key=lambda r: as_date(r["expiry"]))
    if not futures:
        raise LookupError(f"no live {index} futures in the NFO instrument dump")

    options: dict[tuple[date, float, str], OptionInfo] = {}
    for r in rows:
        if r["segment"] == "NFO-OPT" and r.get("instrument_type") in ("CE", "PE"):
            opt = OptionInfo(int(r["instrument_token"]), r["tradingsymbol"], as_date(r["expiry"]),
                             float(r["strike"]), r["instrument_type"], int(r["lot_size"]))
            options[(opt.expiry, opt.strike, opt.right)] = opt
    if not options:
        raise LookupError(f"no live {index} options in the NFO instrument dump")

    expiries = sorted({exp for exp, _, _ in options})
    nearest = [o for o in options.values() if o.expiry == expiries[0]]
    strikes = sorted({o.strike for o in nearest})
    around = spot_price or strikes[len(strikes) // 2]

    return IndexReference(
        index=index,
        spot_token=spot_token,
        future_token=int(futures[0]["instrument_token"]),
        future_symbol=futures[0]["tradingsymbol"],
        future_expiry=as_date(futures[0]["expiry"]),
        expiries=expiries,
        lot_size=Counter(o.lot_size for o in nearest).most_common(1)[0][0],
        strike_step=infer_strike_step(strikes, around),
        options=options,
    )
