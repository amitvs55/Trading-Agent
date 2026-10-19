"""Read what a person types ("Nifty 19th Oct 22950 ce") and find the listed contract it means.

Understands an index name (NIFTY by default), an expiry ("19 Oct", "19th October", "19/10",
"2026-10-19", "this week", "next week", "monthly"), a strike ("22950", "22,950") and a side
("CE", "call", "PE", "put"), in any order, or an exchange symbol ("NIFTY26OCT22950CE"). Whatever
is missing or not listed comes back as a clear problem with the nearest real contracts instead.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from options.core.calendar import IST
from options.reference import IndexReference, OptionInfo

INDEX_ALIASES = {
    "NIFTY": ("nifty 50", "nifty50", "nifty", "nf"),
    "BANKNIFTY": ("bank nifty", "banknifty", "nifty bank", "bn"),
    "FINNIFTY": ("fin nifty", "finnifty", "nifty fin service", "fn"),
    "SENSEX": ("sensex",),
}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
RIGHTS = {"ce": "CE", "call": "CE", "calls": "CE", "c": "CE", "pe": "PE", "put": "PE", "puts": "PE", "p": "PE"}


@dataclass
class Query:
    text: str
    index: str | None = None
    expiry: date | None = None
    expiry_word: str | None = None          # "this week" | "next week" | "monthly"
    strike: float | None = None
    right: str | None = None
    symbol: str | None = None               # squashed text, tried as an exchange symbol


@dataclass
class Resolved:
    option: OptionInfo | None
    query: Query
    problem: str | None = None
    suggestions: list[OptionInfo] = field(default_factory=list)


def _year_for(day: int, month: int, today: date) -> date | None:
    """The next date with this day and month (today counts), so "19 Oct" in December means next year."""
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d >= today:
            return d
    try:
        return date(today.year, month, day)                 # in the past: reported as expired
    except ValueError:
        return None


def parse_query(text: str, today: date) -> Query:
    q = Query(text=text.strip())
    s = " " + re.sub(r"[,]", "", text.lower()) + " "
    q.symbol = re.sub(r"[^A-Z0-9]", "", text.upper()) or None

    for index, names in INDEX_ALIASES.items():
        for name in names:
            if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", s):
                q.index = index
                s = re.sub(rf"(?<![a-z]){re.escape(name)}(?![a-z])", " ", s)
                break
        if q.index:
            break

    if re.search(r"\bnext\s*week\b", s):
        q.expiry_word = "next week"
    elif re.search(r"\b(this\s*week|today|weekly|current)\b", s):
        q.expiry_word = "this week"
    elif re.search(r"\b(monthly|month\s*end|this\s*month)\b", s):
        q.expiry_word = "monthly"
    s = re.sub(r"\b(next|this)\s*week\b|\b(today|weekly|current|monthly|month\s*end|this\s*month|expiry)\b", " ", s)

    month_names = "|".join(f"{m}[a-z]*" for m in MONTHS)
    patterns = [
        (rf"\b(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})\b", lambda m: _date(int(m[3]), int(m[2]), int(m[1]))),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.]*({month_names})[\s\-/.]*(\d{{2,4}})?\b",
         lambda m: _dm(int(m[1]), MONTHS[m[2][:3]], m[3], today)),
        (rf"\b({month_names})[\s\-/.]*(\d{{1,2}})(?:st|nd|rd|th)?\b(?![\d])",
         lambda m: _dm(int(m[2]), MONTHS[m[1][:3]], None, today)),
        (r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", lambda m: _dm(int(m[1]), int(m[2]), m[3], today)),
    ]
    for pattern, make in patterns:
        m = re.search(pattern, s)
        if m:
            q.expiry = make(m)
            s = s[:m.start()] + " " + s[m.end():]
            break

    for word, right in RIGHTS.items():
        if re.search(rf"(?<![a-z]){word}(?![a-z])", s) or re.search(rf"\d{word}\b", s):
            q.right = right
            s = re.sub(rf"(?<=\d){word}\b|(?<![a-z]){word}(?![a-z])", " ", s)
            break

    nums = [float(n) for n in re.findall(r"(?<![\d.])(\d{3,6}(?:\.\d+)?)(?![\d])", s)]
    strikes = [n for n in nums if n >= 100]
    if strikes:
        q.strike = strikes[0]
    return q


def _date(day: int, month: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _dm(day: int, month: int, year: str | None, today: date) -> date | None:
    if not (1 <= month <= 12):
        return None
    if year:
        y = int(year)
        return _date(day, month, y + 2000 if y < 100 else y)
    return _year_for(day, month, today)


def _nearest(items: list, value: float, n: int) -> list:
    return sorted(items, key=lambda x: abs(x - value))[:n]


def resolve(query: Query, refs: dict[str, IndexReference], now: datetime) -> Resolved:
    today = now.astimezone(IST).date()
    index = query.index or ("NIFTY" if "NIFTY" in refs else next(iter(refs), None))
    if query.index and query.index not in refs:
        return Resolved(None, query, f"{query.index} options aren't covered yet (only {', '.join(refs) or 'none'})")
    ref = refs.get(index) if index else None
    if ref is None:
        return Resolved(None, query, "No contract list is loaded yet")
    query.index = index

    # An exact exchange symbol wins
    if query.symbol:
        for opt in ref.options.values():
            if opt.tradingsymbol.upper() == query.symbol:
                query.expiry, query.strike, query.right = opt.expiry, opt.strike, opt.right
                return _check_expired(Resolved(opt, query), now)

    local = now.astimezone(IST)
    expiries = sorted(e for e in ref.expiries                     # still tradable now
                      if e > local.date() or (e == local.date() and (local.hour, local.minute) < (15, 30)))
    if query.expiry_word == "this week":
        query.expiry = expiries[0] if expiries else None
    elif query.expiry_word == "next week":
        query.expiry = expiries[1] if len(expiries) > 1 else None
    elif query.expiry_word == "monthly":
        query.expiry = ref.future_expiry if ref.future_expiry in expiries else next(
            (e for e in expiries if e.month == (expiries[0].month if expiries else 0)), None)

    if query.expiry is not None and (query.expiry < today or (query.expiry == today and query.expiry not in expiries)):
        return Resolved(None, query, f"{query.expiry:%d %b %Y} has passed; that contract has expired",
                        _around(ref, expiries[0], query.strike, query.right) if expiries else [])
    if query.expiry is not None and query.expiry not in expiries:
        listed = [e for e in expiries if abs((e - query.expiry).days) <= 7][:3] or expiries[:3]
        return Resolved(None, query, f"{query.index} has no expiry on {query.expiry:%a %d %b} "
                                     f"(listed: {', '.join(f'{e:%d %b}' for e in listed)})",
                        [o for e in listed for o in _around(ref, e, query.strike, query.right, 1)])
    expiry = query.expiry or (expiries[0] if expiries else None)
    if expiry is None:
        return Resolved(None, query, "No listed expiries")
    query.expiry = expiry

    if query.strike is None:
        return Resolved(None, query, "Which strike? e.g. 22950", _around(ref, expiry, None, query.right))
    strikes = ref.strikes(expiry)
    if query.strike not in strikes:
        near = _nearest(strikes, query.strike, 2)
        return Resolved(None, query, f"{query.strike:g} isn't a listed strike for {expiry:%d %b} "
                                     f"(nearest: {', '.join(f'{k:g}' for k in near)})",
                        [o for k in near for o in _rights(ref, expiry, k, query.right)])
    if query.right is None:
        return Resolved(None, query, "CE (call) or PE (put)?", _rights(ref, expiry, query.strike, None))
    opt = ref.options.get((expiry, query.strike, query.right))
    if opt is None:
        return Resolved(None, query, "That contract isn't listed", _rights(ref, expiry, query.strike, None))
    return _check_expired(Resolved(opt, query), now)


def _check_expired(res: Resolved, now: datetime) -> Resolved:
    opt = res.option
    local = now.astimezone(IST)
    if opt and opt.expiry == local.date() and (local.hour, local.minute) >= (15, 30):
        res.problem = f"{opt.tradingsymbol} expired today at 15:30"
    return res


def _rights(ref: IndexReference, expiry: date, strike: float, right: str | None) -> list[OptionInfo]:
    return [o for rt in ((right,) if right else ("CE", "PE")) if (o := ref.options.get((expiry, strike, rt)))]


def _around(ref: IndexReference, expiry: date, strike: float | None, right: str | None, n: int = 2) -> list[OptionInfo]:
    strikes = ref.strikes(expiry)
    if not strikes:
        return []
    centre = strike if strike is not None else strikes[len(strikes) // 2]
    return [o for k in _nearest(strikes, centre, n) for o in _rights(ref, expiry, k, right)]


def describe(opt: OptionInfo) -> str:
    return f"{opt.tradingsymbol} · {opt.expiry:%d %b %Y} {opt.strike:g} {opt.right} · lot {opt.lot_size}"
