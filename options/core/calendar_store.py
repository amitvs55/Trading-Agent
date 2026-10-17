"""Holidays and events added from the Connectors page, merged with the built-in lists.

NSE publishes next year's holidays in December and the RBI its MPC dates once a year, so
both change without a code release. They are kept as JSON in app_meta:

    calendar_holidays: {"holidays": [{"date": "2027-01-26", "name": "Republic Day"}], "complete_years": [2027]}
    calendar_events:   [{"id": "a1b2c3", "name": "RBI MPC decision", "at": "2027-04-07T10:00:00+05:30", "impact": "high"}]
"""

import json
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine

from options.core.calendar import IST, NseCalendar
from options.core.events import EVENTS, Event
from options.core.holidays import NSE_HOLIDAYS
from options.storage import app_meta

HOLIDAYS_KEY, EVENTS_KEY = "calendar_holidays", "calendar_events"
IMPACTS = ("high", "medium")


def _meta(engine: Engine, key: str):
    with engine.connect() as conn:
        raw = conn.execute(select(app_meta.c.value).where(app_meta.c.key == key)).scalar()
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def saved_holidays(engine: Engine) -> dict:
    data = _meta(engine, HOLIDAYS_KEY) or {}
    return {"holidays": list(data.get("holidays", [])), "complete_years": sorted(set(data.get("complete_years", [])))}


def saved_events(engine: Engine) -> list[dict]:
    return list(_meta(engine, EVENTS_KEY) or [])


def calendar_from_db(engine: Engine) -> NseCalendar:
    saved = saved_holidays(engine)
    by_year: dict[int, set[date]] = {y: set(d) for y, d in NSE_HOLIDAYS.items()}
    for h in saved["holidays"]:
        d = date.fromisoformat(h["date"])
        by_year.setdefault(d.year, set()).add(d)
    complete = set(NSE_HOLIDAYS) | set(saved["complete_years"])
    return NseCalendar({y: frozenset(d) for y, d in by_year.items()}, complete_years=complete)


def events_from_db(engine: Engine) -> list[Event]:
    out = list(EVENTS)
    for e in saved_events(engine):
        at = datetime.fromisoformat(e["at"])
        out.append(Event(e["name"], at if at.tzinfo else at.replace(tzinfo=IST), e.get("impact", "high")))
    return sorted(out, key=lambda e: e.at)


# ── Edits (API, admin only) ─────────────────────────────────────────────────

def add_holiday(repo, d: date, name: str) -> None:
    data = saved_holidays(repo.engine)
    if d.weekday() >= 5:
        raise ValueError("That's a weekend; only weekday holidays need adding.")
    if any(h["date"] == d.isoformat() for h in data["holidays"]) or d in NSE_HOLIDAYS.get(d.year, ()):
        raise ValueError(f"{d:%d %b %Y} is already a holiday.")
    data["holidays"] = sorted([*data["holidays"], {"date": d.isoformat(), "name": name.strip()[:80]}],
                              key=lambda h: h["date"])
    repo.set_meta_json(HOLIDAYS_KEY, data)


def remove_holiday(repo, d: date) -> None:
    data = saved_holidays(repo.engine)
    kept = [h for h in data["holidays"] if h["date"] != d.isoformat()]
    if len(kept) == len(data["holidays"]):
        raise KeyError(d.isoformat())
    data["holidays"] = kept
    repo.set_meta_json(HOLIDAYS_KEY, data)


def set_year_complete(repo, year: int, complete: bool) -> None:
    data = saved_holidays(repo.engine)
    years = set(data["complete_years"])
    years.add(year) if complete else years.discard(year)
    data["complete_years"] = sorted(years)
    repo.set_meta_json(HOLIDAYS_KEY, data)


def add_event(repo, name: str, at: datetime, impact: str) -> dict:
    if impact not in IMPACTS:
        raise ValueError(f"impact must be one of {', '.join(IMPACTS)}")
    at = at if at.tzinfo else at.replace(tzinfo=IST)
    event = {"id": uuid.uuid4().hex[:8], "name": name.strip()[:80], "at": at.astimezone(IST).isoformat(),
             "impact": impact}
    repo.set_meta_json(EVENTS_KEY, sorted([*saved_events(repo.engine), event], key=lambda e: e["at"]))
    return event


def remove_event(repo, event_id: str) -> None:
    events = saved_events(repo.engine)
    kept = [e for e in events if e["id"] != event_id]
    if len(kept) == len(events):
        raise KeyError(event_id)
    repo.set_meta_json(EVENTS_KEY, kept)


def calendar_view(repo, today: date) -> dict:
    saved = saved_holidays(repo.engine)
    cal = calendar_from_db(repo.engine)
    holidays = [{"date": d.isoformat(), "name": None, "source": "built-in"}
                for y in sorted(NSE_HOLIDAYS) for d in sorted(NSE_HOLIDAYS[y])]
    holidays += [{**h, "source": "added"} for h in saved["holidays"]]
    years = sorted({today.year, today.year + 1} | set(NSE_HOLIDAYS) | {int(h["date"][:4]) for h in saved["holidays"]})
    events = [{"id": None, "name": e.name, "at": e.at.isoformat(), "impact": e.impact, "source": "built-in"}
              for e in EVENTS]
    events += [{**e, "source": "added"} for e in saved_events(repo.engine)]
    return {
        "holidays": sorted(holidays, key=lambda h: h["date"]),
        "years": [{"year": y, "complete": cal.has_year(y), "built_in": y in NSE_HOLIDAYS,
                   "count": sum(1 for h in holidays if h["date"].startswith(str(y)))} for y in years],
        "events": sorted(events, key=lambda e: e["at"]),
        "warning": (f"No NSE holiday list for {today.year + 1} yet. NSE publishes it in December; add it here "
                    f"before 1 Jan, then mark the year complete."
                    if not cal.has_year(today.year + 1) and today.month == 12 else
                    None if cal.has_year(today.year) else
                    f"No NSE holiday list for {today.year}: every weekday is treated as a trading day."),
    }
