"""News agent (pillar 12): official announcements that move the index, read from RSS.

Source: the RBI's press-release feed (https://rbi.org.in/pressreleases_rss.xml). It carries
publish times to the minute and covers the unscheduled actions that move NIFTY options: policy
rate changes, CRR/SLR changes, the Governor's statements. Scheduled decisions are already in the
events calendar; this catches the ones nobody scheduled. (SEBI's feed has dates but no times and
is mostly appeal orders; PIB's feed was unreliable when checked on 17 Oct 2026, so neither is used.)

Each headline is classified by explicit rules, never by an LLM:
- **high**: policy and reserve-ratio actions, so no new entries for 15 minutes after one;
- **medium**: forex, inflation and OMO announcements, a caution for 30 minutes;
- **routine**: auctions, results, statistics, licences and penalties, which are ignored.
Headlines are only matched against these patterns; their text never reaches a model.
"""

import re
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable

import requests

from options.agents.context import AgentContext
from options.core.calendar import IST, now_ist
from options.core.schemas import PillarView
from utils.logger import setup_logger

logger = setup_logger("options.news")

FEEDS = {"RBI": "https://rbi.org.in/pressreleases_rss.xml"}
POLL_S = 120
BLOCK_FOR = timedelta(minutes=15)       # after a high-impact release
CAUTION_FOR = timedelta(minutes=30)     # after a medium one
LOOKBACK = timedelta(hours=1)

ROUTINE = re.compile(r"treasury bills?|money market operations|auction|result|sovereign gold bond|penalt|"
                     r"amalgamation|cancell?ation|certificate of registration|reference rate|weekly statistical|"
                     r"minutes of the|appeal|draft|lending rate|survey|directions|compounding|ombudsman", re.I)
HIGH = re.compile(r"monetary policy|policy repo|repo rate|reverse repo|cash reserve ratio|\bcrr\b|"
                  r"statutory liquidity ratio|\bslr\b|governor'?s statement|bank rate|marginal standing facility|"
                  r"standing deposit facility|rate (cut|hike)|policy rate", re.I)
MEDIUM = re.compile(r"open market operation|\bomo\b|foreign exchange|forex|exchange rate|rupee|inflation|"
                    r"\bcpi\b|\bgdp\b|liquidity measures?|special (repo|liquidity)", re.I)


@dataclass(frozen=True)
class NewsItem:
    source: str
    title: str
    published: datetime          # IST
    impact: str                  # high | medium | routine


def classify(title: str) -> str:
    if ROUTINE.search(title):
        return "routine"
    if HIGH.search(title):
        return "high"
    if MEDIUM.search(title):
        return "medium"
    return "routine"


def _published(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)                  # "Fri, 16 Oct 2026 18:30:00" (RBI publishes IST, no zone)
    except (TypeError, ValueError):
        for fmt in ("%d %b, %Y %z", "%d %b %Y %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def parse_rss(raw: bytes, source: str) -> list[NewsItem]:
    root = ET.fromstring(raw.lstrip(b"\xef\xbb\xbf").strip())
    out = []
    for item in root.iter("item"):
        title = re.sub(r"\s+", " ", (item.findtext("title") or "")).strip()
        published = _published(item.findtext("pubDate"))
        if title and published:
            out.append(NewsItem(source, title[:300], published, classify(title)))
    return out


def fetch_feeds(session: requests.Session | None = None) -> tuple[list[NewsItem], list[str]]:
    """(items from every feed that answered, names of the feeds that didn't)."""
    http = session or requests.Session()
    items, failed = [], []
    for source, url in FEEDS.items():
        try:
            resp = http.get(url, timeout=15, headers={"User-Agent": "TradingAgents/1.0 (+news pillar)"})
            resp.raise_for_status()
            items += parse_rss(resp.content, source)
        except Exception as e:
            logger.warning("News feed %s failed: %s", source, type(e).__name__)
            failed.append(source)
    return items, failed


class NewsFetcher:
    """Polls the feeds in a background thread; the engine reads the latest snapshot."""

    def __init__(self, fetch: Callable[[], tuple[list[NewsItem], list[str]]] = fetch_feeds, every_s: int = POLL_S,
                 now_fn: Callable[[], datetime] = now_ist):
        self._fetch, self._every, self._now = fetch, every_s, now_fn
        self._lock = threading.Lock()
        self._snap: dict | None = None
        self._stop = threading.Event()

    def refresh(self) -> None:
        try:
            items, failed = self._fetch()
        except Exception as e:
            logger.warning("news refresh failed: %s", type(e).__name__)
            items, failed = [], list(FEEDS)
        with self._lock:
            if items or not self._snap:
                self._snap = {"items": items, "failed": failed, "fetched_at": self._now()}
            else:                                       # keep the last good items through a failed poll
                self._snap = {**self._snap, "failed": failed}

    def snapshot(self) -> dict | None:
        with self._lock:
            return dict(self._snap) if self._snap else None

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self._every)
        threading.Thread(target=loop, name="news", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def analyse(ctx: AgentContext) -> PillarView:
    snap = ctx.news
    if not snap or (not snap.get("items") and snap.get("failed")):
        return PillarView("news", "News feed unreachable (RBI press releases)", status="na")
    now = ctx.now.astimezone(IST)
    fresh = sorted((i for i in snap["items"] if timedelta(0) <= now - i.published <= LOOKBACK),
                   key=lambda i: i.published, reverse=True)
    stale_note = " (feed check failed, last good read shown)" if snap.get("failed") else ""
    for item in fresh:
        age = now - item.published
        mins = int(age.total_seconds() // 60)
        if item.impact == "high" and age <= BLOCK_FOR:
            return PillarView("news", f"{item.source}: {item.title} ({mins} min ago): no new entries for "
                                      f"{int((BLOCK_FOR - age).total_seconds() // 60) + 1} min{stale_note}",
                              status="fail", features={"title": item.title, "minutes_ago": mins})
    for item in fresh:
        age = now - item.published
        if item.impact == "high" or (item.impact == "medium" and age <= CAUTION_FOR):
            return PillarView("news", f"{item.source}: {item.title} ({int(age.total_seconds() // 60)} min ago)"
                                      f"{stale_note}", status="warn", features={"title": item.title})
    return PillarView("news", f"No market-moving RBI announcement in the last hour{stale_note}", status="pass")
