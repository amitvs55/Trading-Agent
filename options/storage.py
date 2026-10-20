"""Persistence: Kite sessions, daily instrument snapshots, 1-minute bars and session events.

Postgres on Railway, SQLite locally and in tests. Kite drops expired contracts from its
instrument dump, so the daily snapshot is what lets old bars be mapped back to strikes.
"""

from datetime import date, datetime
from pathlib import Path

import json

from sqlalchemy import (BigInteger, Column, Date, DateTime, Float, Index, Integer, MetaData, String,
                        Table, Text, create_engine, delete, func, select, text, update)
from sqlalchemy.engine import Engine

from options.core.schemas import OPEN_STATES, Signal
from options.reference import as_date

LIVE_KEY = "live_indices"           # app_meta row with the latest index levels
LIVE_CHANNEL = "live_indices"       # Postgres NOTIFY channel the API listens on

metadata = MetaData()

kite_sessions = Table(
    "kite_sessions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trading_date", Date, nullable=False, index=True),
    Column("access_token", Text, nullable=False),
    Column("user_id", String(32)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

instruments_daily = Table(
    "instruments_daily", metadata,
    Column("trading_date", Date, primary_key=True),
    Column("instrument_token", BigInteger, primary_key=True),
    Column("tradingsymbol", String(64), nullable=False),
    Column("name", String(32)),
    Column("segment", String(16)),
    Column("instrument_type", String(8)),
    Column("expiry", Date),
    Column("strike", Float),
    Column("lot_size", Integer),
    Column("tick_size", Float),
)

bars_1m = Table(
    "bars_1m", metadata,
    Column("instrument_token", BigInteger, primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),   # minute start, IST
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
    Column("volume_day", BigInteger),                            # cumulative day volume at bar close
    Column("oi", BigInteger),
    Column("bid", Float),
    Column("ask", Float),
    Column("bid_qty", BigInteger),
    Column("ask_qty", BigInteger),
    Column("ticks", Integer, nullable=False),
)
# The primary key leads with the token, so "latest bar" and "bars since" need their own index on ts
Index("ix_bars_1m_ts", bars_1m.c.ts)

session_events = Table(
    "session_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("detail", Text),
)

signals = Table(
    "signals", metadata,
    Column("signal_id", String(32), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("index_name", String(16), nullable=False),
    Column("setup", String(32), nullable=False),
    Column("horizon", String(12), nullable=False),
    Column("grade", String(1), nullable=False),
    Column("mode", String(8), nullable=False),
    Column("state", String(12), nullable=False, index=True),
    Column("data", Text, nullable=False),                       # full Signal JSON
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

signal_events = Table(
    "signal_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("signal_id", String(32), nullable=False, index=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("price", Float),
    Column("message", Text),
)

# Candidates that were evaluated but not sent (gates failed or grade C): the "why no trade" log
evaluations = Table(
    "evaluations", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False, index=True),
    Column("index_name", String(16), nullable=False),
    Column("setup", String(32), nullable=False),
    Column("side", Integer, nullable=False),
    Column("grade", String(1)),
    Column("score", Float),
    Column("outcome", String(16), nullable=False),               # SIGNAL | NO_TRADE | GRADE_C | OVER_BUDGET
    Column("reasons", Text),
)

# Latest board (all pillars) per index, for the dashboard
board_state = Table(
    "board_state", metadata,
    Column("index_name", String(16), primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("data", Text, nullable=False),
)

# Latest health of each group of agents: an index's signal agents ("NIFTY"), the research
# pipeline's agents ("research") and the last self-test ("selftest")
agent_status = Table(
    "agent_status", metadata,
    Column("key", String(32), primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("data", Text, nullable=False),
)

# ── Admin: accounts, sessions, settings saved from the UI, health results ──────────

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True)),
    Column("full_name", String(80)),                               # shown in the navbar, e.g. "Amit Shinde"
    Column("disabled", Integer, nullable=False, server_default="0"),
)

user_sessions = Table(
    "user_sessions", metadata,
    Column("token_digest", String(64), primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)

app_settings = Table(
    "app_settings", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),            # JSON; Fernet-encrypted when secret
    Column("secret", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(64)),
)

app_meta = Table(
    "app_meta", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

health_checks = Table(
    "health_checks", metadata,
    Column("check_id", String(32), primary_key=True),
    Column("status", String(8), nullable=False),
    Column("message", Text, nullable=False),
    Column("details", Text),
    Column("latency_ms", Integer),
    Column("checked_at", DateTime(timezone=True), nullable=False),
)

# Every alert goes here first; a background sender delivers it, so a slow or failing channel
# never holds up the signal engine and nothing is lost if the process restarts
alerts_outbox = Table(
    "alerts_outbox", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("digest", String(64), nullable=False, index=True),      # same text within a short window = duplicate
    Column("text", Text, nullable=False),
    Column("buttons", Text),                                        # JSON [[label, url], …]
    Column("status", String(10), nullable=False, index=True),      # pending | sent | failed | expired
    Column("channel", String(16)),                                  # who delivered it: telegram | email
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    Column("sent_at", DateTime(timezone=True)),
)

# Research pipeline runs (the old app's 13-agent analysis). Used to live in logs/trades.jsonl on
# the container's disk, which every redeploy wiped; History and Usage read this table now.
research_runs = Table(
    "research_runs", metadata,
    Column("run_id", String(16), primary_key=True),
    Column("ticker", String(32), nullable=False, index=True),
    Column("exchange", String(8), nullable=False),
    Column("requested_by", String(64)),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", String(12), nullable=False),            # running | done | failed | cancelled
    Column("action", String(12)),                              # execute | hold | reject
    Column("order_status", String(24)),                        # executed_simulated | held | rejected
    Column("order_id", String(16)),
    Column("entry", Float), Column("stop_loss", Float), Column("take_profit", Float), Column("size_pct", Float),
    Column("details", Text),
    Column("model", String(80)),
    Column("total_tokens", Integer), Column("cost_usd", Float),
    Column("usage", Text),                                     # UsageSummary JSON
    Column("decision", Text),                                  # FinalDecision JSON
    Column("error", Text),
)

# Every LLM call of a research run, prompt and answer included, so any decision can be audited
# and replayed (review finding F-16)
research_llm_calls = Table(
    "research_llm_calls", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(16), nullable=False, index=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("agent", String(48), nullable=False),
    Column("model", String(80), nullable=False),
    Column("temperature", Float),
    Column("seed", Integer),
    Column("system_prompt", Text),
    Column("user_prompt", Text),
    Column("response", Text),
    Column("prompt_tokens", Integer), Column("completion_tokens", Integer),
    Column("is_retry", Integer, nullable=False, server_default="0"),
)

# Option Check: one row per check. During market hours the API leaves it "pending" and the recorder
# fills in the market facts from the live engine; the report is rebuilt from facts + parameters, so
# what-ifs never touch the recorder. Outcomes are filled in later from the saved bars (the checker's
# own track record), and a check can be followed as a paper trade.
option_checks = Table(
    "option_checks", metadata,
    Column("id", String(16), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("username", String(64)),
    Column("query", String(200), nullable=False),
    Column("index_name", String(16)),
    Column("symbol", String(64)),
    Column("token", BigInteger),
    Column("expiry", Date),
    Column("strike", Float),
    Column("option_right", String(2)),
    Column("lot_size", Integer),
    Column("status", String(12), nullable=False),          # pending | done | error
    Column("error", Text),
    Column("params", Text),                                # JSON: amount, entry, horizon, …
    Column("facts", Text),                                 # JSON from options/check/facts.py
    Column("summary", Text),                               # JSON: verdict, entry, units, probabilities, horizon end
    Column("outcome", Text),                               # JSON: what actually happened
    Column("outcome_done", Integer, nullable=False, default=0),
    Column("paper", Integer, nullable=False, default=0),
    Column("paper_entry", Float),
    Column("paper_units", Integer),
    Column("paper_exit", Float),
    Column("paper_closed_at", DateTime(timezone=True)),
)

# The paper trading desk (options/desk): each user's virtual funds, and every order they place.
# Positions, P&L and cash are rebuilt from the filled orders on every read, so they can't drift.
# A reset starts a new epoch: older orders stay in the table but no longer count.
desk_accounts = Table(
    "desk_accounts", metadata,
    Column("username", String(64), primary_key=True),
    Column("funds", Float, nullable=False),                  # starting funds of the current epoch
    Column("added", Float, nullable=False, server_default="0"),
    Column("epoch", Integer, nullable=False, server_default="1"),
    Column("started_at", DateTime(timezone=True), nullable=False),
)

desk_orders = Table(
    "desk_orders", metadata,
    Column("id", String(64), primary_key=True),
    Column("username", String(64), nullable=False, index=True),
    Column("epoch", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("index_name", String(16)),
    Column("symbol", String(64), nullable=False),
    Column("token", BigInteger, nullable=False),
    Column("spot_token", BigInteger),                        # the index, for expiry settlement
    Column("expiry", Date),
    Column("strike", Float),
    Column("option_right", String(2)),
    Column("lot_size", Integer, nullable=False),
    Column("side", String(4), nullable=False),               # BUY | SELL
    Column("product", String(4), nullable=False),            # MIS (intraday) | NRML (carry)
    Column("order_type", String(6), nullable=False),         # MARKET | LIMIT | SL | SL-M
    Column("qty", Integer, nullable=False),                  # units, a whole number of lots
    Column("price", Float),                                  # limit price (LIMIT, SL)
    Column("trigger_price", Float),                          # SL, SL-M
    Column("status", String(10), nullable=False, index=True),
    Column("reason", Text),                                  # why rejected or cancelled
    Column("block", Float),                                  # funds held for a buy until it fills or ends
    Column("fill_price", Float),
    Column("filled_at", DateTime(timezone=True)),
    Column("fill_source", String(40)),                       # live ask, live bid, settlement, …
    Column("charges", Text),                                 # JSON breakdown of this order's charges
    Column("source", String(40)),                            # ticket | signal:<id> | exit | squareoff | expiry
)

# One row per minute of a recording session: is the machine keeping up? (review F-28 / roadmap R-28)
session_metrics = Table(
    "session_metrics", metadata,
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("ticks", Integer, nullable=False),            # ticks received in the minute
    Column("bars", Integer, nullable=False),             # bars saved in the minute
    Column("rejected_ticks", Integer, nullable=False),
    Column("eval_ms", Float),                            # slowest signal evaluation in the minute
    Column("alert_delay_s", Float),                      # slowest alert delivery in the minute
    Column("open_signals", Integer),
    Column("live_lag_ms", Float),                        # exchange tick → pushed to the dashboard, p95
)

# Failed sign-in and setup attempts, so the brute-force limit survives an API restart or redeploy
auth_failures = Table(
    "auth_failures", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key", String(200), nullable=False, index=True),
    Column("ts", DateTime(timezone=True), nullable=False, index=True),
)

# Who changed what, and when: trading rules, pauses, calendars, users
audit_log = Table(
    "audit_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False, index=True),
    Column("actor", String(64), nullable=False),
    Column("action", String(48), nullable=False),
    Column("detail", Text),
)

_INSTRUMENT_FIELDS = ("instrument_token", "tradingsymbol", "name", "segment", "instrument_type",
                      "strike", "lot_size", "tick_size")


def normalize_db_url(url: str) -> str:
    """Railway hands out postgres:// URLs; SQLAlchemy needs the psycopg (v3) driver named."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_db_url(url)
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True)
    metadata.create_all(engine)
    _add_missing_columns(engine)
    _add_missing_indexes(engine)
    return engine


def _add_missing_indexes(engine: Engine) -> None:
    """create_all() only indexes tables it creates; indexes added later go onto existing tables here."""
    for table in metadata.sorted_tables:
        for index in table.indexes:
            index.create(engine, checkfirst=True)


# Columns added after a table already existed in production: create_all() only creates
# missing tables, so these are added in place (nullable or with a default, so it is safe).
_LATER_COLUMNS = {"users": [("full_name", "VARCHAR(80)"), ("disabled", "INTEGER NOT NULL DEFAULT 0")],
                  "session_metrics": [("live_lag_ms", "FLOAT")]}


def _add_missing_columns(engine: Engine) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    for table, cols in _LATER_COLUMNS.items():
        if not insp.has_table(table):
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


class Store:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _upsert(self, table: Table, rows: list[dict], keys: list[str]) -> int:
        if not rows:
            return 0
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
            chunk = max(1, 30_000 // len(table.columns))
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
            chunk = max(1, 900 // len(table.columns))
        else:
            raise NotImplementedError(f"upsert not implemented for {dialect}")
        with self.engine.begin() as conn:
            for i in range(0, len(rows), chunk):
                stmt = insert(table).values(rows[i:i + chunk])
                update = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys}
                conn.execute(stmt.on_conflict_do_update(index_elements=keys, set_=update))
        return len(rows)

    # ── Kite sessions ─────────────────────────────────────────────────────────

    def save_access_token(self, trading_date: date, access_token: str, user_id: str | None,
                          now: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(kite_sessions.insert().values(
                trading_date=trading_date, access_token=access_token, user_id=user_id, created_at=now))

    def load_access_token(self, trading_date: date) -> str | None:
        """Latest token saved for the trading date (Kite tokens expire early the next morning)."""
        q = (select(kite_sessions.c.access_token)
             .where(kite_sessions.c.trading_date == trading_date)
             .order_by(kite_sessions.c.id.desc()).limit(1))
        with self.engine.connect() as conn:
            return conn.execute(q).scalar()

    # ── Instruments, bars, events ─────────────────────────────────────────────

    def save_instruments(self, trading_date: date, rows: list[dict]) -> int:
        out = [{"trading_date": trading_date, "expiry": as_date(r.get("expiry")),
                **{k: r.get(k) for k in _INSTRUMENT_FIELDS}} for r in rows]
        return self._upsert(instruments_daily, out, ["trading_date", "instrument_token"])

    def instruments_on(self, trading_date: date) -> list[dict]:
        q = select(instruments_daily).where(instruments_daily.c.trading_date == trading_date)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def recorded_days(self) -> list[date]:
        q = select(instruments_daily.c.trading_date).distinct().order_by(instruments_daily.c.trading_date)
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(q)]

    def bars_between(self, start: datetime, end: datetime, tokens: set[int] | None = None) -> list[dict]:
        q = select(bars_1m).where(bars_1m.c.ts >= start, bars_1m.c.ts < end)
        if tokens is not None:
            q = q.where(bars_1m.c.instrument_token.in_(sorted(tokens)))
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q.order_by(bars_1m.c.ts, bars_1m.c.instrument_token))]

    def write_bars(self, rows: list[dict]) -> int:
        return self._upsert(bars_1m, rows, ["instrument_token", "ts"])

    def insert_bars_if_missing(self, rows: list[dict]) -> int:
        """Warm-up history: kept so replays see what the live engine saw, but never over a recorded bar."""
        if not rows:
            return 0
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
            chunk = max(1, 30_000 // len(bars_1m.columns))
        else:
            from sqlalchemy.dialects.sqlite import insert
            chunk = max(1, 900 // len(bars_1m.columns))
        with self.engine.begin() as conn:
            for i in range(0, len(rows), chunk):
                conn.execute(insert(bars_1m).values(rows[i:i + chunk]).on_conflict_do_nothing(
                    index_elements=["instrument_token", "ts"]))
        return len(rows)

    def log_event(self, kind: str, detail: str, now: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(session_events.insert().values(ts=now, kind=kind, detail=detail[:2000]))

    def count_bars_since(self, since: datetime) -> int:
        q = select(func.count()).select_from(bars_1m).where(bars_1m.c.ts >= since)
        with self.engine.connect() as conn:
            return conn.execute(q).scalar() or 0

    def latest_bar(self, token: int) -> dict | None:
        q = (select(bars_1m).where(bars_1m.c.instrument_token == token)
             .order_by(bars_1m.c.ts.desc()).limit(1))
        with self.engine.connect() as conn:
            row = conn.execute(q).first()
        return dict(row._mapping) if row else None

    def last_bar_ts(self) -> datetime | None:
        with self.engine.connect() as conn:
            return conn.execute(select(func.max(bars_1m.c.ts))).scalar()

    def latest_token(self, tradingsymbol: str) -> int | None:
        """Instrument token of a symbol (e.g. "NIFTY 50") from the newest daily snapshot."""
        q = (select(instruments_daily.c.instrument_token).where(instruments_daily.c.tradingsymbol == tradingsymbol)
             .order_by(instruments_daily.c.trading_date.desc()).limit(1))
        with self.engine.connect() as conn:
            tok = conn.execute(q).scalar()
        return int(tok) if tok is not None else None

    def close_near(self, token: int, at: datetime, before: bool = True) -> float | None:
        """The last close at or before `at` (or the first at or after it)."""
        q = select(bars_1m.c.close).where(bars_1m.c.instrument_token == token)
        q = (q.where(bars_1m.c.ts <= at).order_by(bars_1m.c.ts.desc()) if before
             else q.where(bars_1m.c.ts >= at).order_by(bars_1m.c.ts))
        with self.engine.connect() as conn:
            v = conn.execute(q.limit(1)).scalar()
        return float(v) if v is not None else None

    def bar_counts_per_day(self, token: int, start: datetime, end: datetime) -> dict[date, int]:
        """Saved minutes per day for one instrument (market hours fall on the same date in UTC and IST)."""
        day = func.date(bars_1m.c.ts)
        q = (select(day, func.count()).where(bars_1m.c.instrument_token == token, bars_1m.c.ts >= start,
                                             bars_1m.c.ts < end).group_by(day))
        with self.engine.connect() as conn:
            return {(d if isinstance(d, date) else date.fromisoformat(str(d)[:10])): n for d, n in conn.execute(q)}

    def bar_counts_between(self, start: datetime, end: datetime) -> dict[int, int]:
        """Minutes recorded per instrument: the daily completeness report."""
        q = (select(bars_1m.c.instrument_token, func.count())
             .where(bars_1m.c.ts >= start, bars_1m.c.ts < end).group_by(bars_1m.c.instrument_token))
        with self.engine.connect() as conn:
            return {int(t): int(n) for t, n in conn.execute(q)}

    def purge_before(self, bars_cutoff: datetime, logs_cutoff: datetime) -> dict[str, int]:
        """Retention: 1-minute bars older than bars_cutoff; delivered alerts, session events and research
        prompts older than logs_cutoff. Signals, their events, evaluations and research run results are
        the track record: never purged."""
        with self.engine.begin() as conn:
            bars = conn.execute(delete(bars_1m).where(bars_1m.c.ts < bars_cutoff)).rowcount
            alerts = conn.execute(delete(alerts_outbox).where(alerts_outbox.c.created_at < logs_cutoff,
                                                              alerts_outbox.c.status != "pending")).rowcount
            events = conn.execute(delete(session_events).where(session_events.c.ts < logs_cutoff)).rowcount
            calls = conn.execute(delete(research_llm_calls).where(research_llm_calls.c.ts < logs_cutoff)).rowcount
            conn.execute(delete(session_metrics).where(session_metrics.c.ts < logs_cutoff))
        return {"bars": bars or 0, "alerts": alerts or 0, "session_events": events or 0, "llm_calls": calls or 0}

    def session_events_since(self, since: datetime, limit: int = 100) -> list[dict]:
        q = (select(session_events).where(session_events.c.ts >= since)
             .order_by(session_events.c.ts.desc(), session_events.c.id.desc()).limit(limit))
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    # ── Small shared facts (app_meta), e.g. the pause switch the API sets and the engine reads ──

    def get_meta_json(self, key: str) -> dict | None:
        with self.engine.connect() as conn:
            raw = conn.execute(select(app_meta.c.value).where(app_meta.c.key == key)).scalar()
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def set_meta_json(self, key: str, value: dict, now: datetime) -> None:
        raw = json.dumps(value, default=str)
        with self.engine.begin() as conn:
            done = conn.execute(update(app_meta).where(app_meta.c.key == key).values(value=raw, updated_at=now)).rowcount
            if not done:
                conn.execute(app_meta.insert().values(key=key, value=raw, updated_at=now))

    # ── Live index levels (recorder → API → dashboard) ───────────────────────

    def publish_live(self, payload: dict, now: datetime, persist: bool = True) -> None:
        """The latest index levels: saved as LIVE_KEY (for a page that has just opened, and for an
        API restart) and, on Postgres, pushed on LIVE_CHANNEL at once, so the API never polls."""
        raw = json.dumps(payload, separators=(",", ":"), default=str)
        with self.engine.begin() as conn:
            if persist:
                done = conn.execute(update(app_meta).where(app_meta.c.key == LIVE_KEY)
                                    .values(value=raw, updated_at=now)).rowcount
                if not done:
                    conn.execute(app_meta.insert().values(key=LIVE_KEY, value=raw, updated_at=now))
            if self.engine.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": LIVE_CHANNEL, "payload": raw})

    def live_snapshot(self) -> dict | None:
        return self.get_meta_json(LIVE_KEY)

    # ── Alerts outbox ────────────────────────────────────────────────────────

    def outbox_add(self, digest: str, text: str, buttons: str | None, now: datetime,
                   duplicate_since: datetime | None = None) -> int | None:
        """Queue an alert; returns its id, or None when the same text was queued since duplicate_since."""
        with self.engine.begin() as conn:
            if duplicate_since is not None and conn.execute(
                    select(alerts_outbox.c.id).where(alerts_outbox.c.digest == digest,
                                                     alerts_outbox.c.created_at >= duplicate_since).limit(1)).first():
                return None
            res = conn.execute(alerts_outbox.insert().values(created_at=now, digest=digest, text=text,
                                                             buttons=buttons, status="pending", attempts=0))
            return int(res.inserted_primary_key[0])

    def outbox_update(self, alert_id: int, **values) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(alerts_outbox).where(alerts_outbox.c.id == alert_id).values(**values))

    def outbox_pending(self, limit: int = 500) -> list[dict]:
        q = (select(alerts_outbox).where(alerts_outbox.c.status == "pending")
             .order_by(alerts_outbox.c.id).limit(limit))
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def outbox_recent(self, limit: int = 50) -> list[dict]:
        q = select(alerts_outbox).order_by(alerts_outbox.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def outbox_counts_since(self, since: datetime) -> dict[str, int]:
        q = (select(alerts_outbox.c.status, func.count()).where(alerts_outbox.c.created_at >= since)
             .group_by(alerts_outbox.c.status))
        with self.engine.connect() as conn:
            return {s: int(n) for s, n in conn.execute(q)}

    # ── Research runs ────────────────────────────────────────────────────────

    def research_start(self, run_id: str, ticker: str, exchange: str, by: str | None, model: str,
                       now: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(research_runs.insert().values(run_id=run_id, ticker=ticker, exchange=exchange,
                                                       requested_by=by, started_at=now, status="running", model=model))

    def research_finish(self, run_id: str, now: datetime, **values) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(research_runs).where(research_runs.c.run_id == run_id)
                         .values(finished_at=now, **values))

    def research_runs(self, *, ticker: str = "", status: str = "", limit: int = 50, offset: int = 0,
                      since: datetime | None = None) -> tuple[int, list[dict]]:
        q = select(research_runs)
        if ticker:
            q = q.where(research_runs.c.ticker.ilike(f"%{ticker.strip()}%"))
        if status:
            q = q.where(research_runs.c.order_status == status)
        if since is not None:
            q = q.where(research_runs.c.started_at >= since)
        with self.engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
            rows = conn.execute(q.order_by(research_runs.c.started_at.desc()).limit(limit).offset(offset)).all()
        return int(total), [dict(r._mapping) for r in rows]

    def research_cost_since(self, since: datetime) -> float:
        q = select(func.coalesce(func.sum(research_runs.c.cost_usd), 0.0)).where(research_runs.c.started_at >= since)
        with self.engine.connect() as conn:
            return float(conn.execute(q).scalar() or 0.0)

    def research_running(self) -> int:
        q = select(func.count()).select_from(research_runs).where(research_runs.c.status == "running")
        with self.engine.connect() as conn:
            return int(conn.execute(q).scalar() or 0)

    def research_log_calls(self, rows: list[dict]) -> None:
        if rows:
            with self.engine.begin() as conn:
                conn.execute(research_llm_calls.insert(), rows)

    def research_calls(self, run_id: str) -> list[dict]:
        q = select(research_llm_calls).where(research_llm_calls.c.run_id == run_id).order_by(research_llm_calls.c.id)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def research_has_order(self, order_id: str) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(select(research_runs.c.run_id).where(research_runs.c.order_id == order_id)).first() is not None

    # ── Option Check ─────────────────────────────────────────────────────────

    _CHECK_JSON = ("params", "facts", "summary", "outcome")

    def _check_row(self, r) -> dict:
        d = dict(r._mapping)
        for k in self._CHECK_JSON:
            try:
                d[k] = json.loads(d[k]) if d.get(k) else None
            except ValueError:
                d[k] = None
        return d

    def check_add(self, row: dict) -> None:
        values = {k: (json.dumps(v, separators=(",", ":"), default=str) if k in self._CHECK_JSON and v is not None else v)
                  for k, v in row.items()}
        with self.engine.begin() as conn:
            conn.execute(option_checks.insert().values(**values))

    def check_update(self, check_id: str, **values) -> None:
        values = {k: (json.dumps(v, separators=(",", ":"), default=str) if k in self._CHECK_JSON and v is not None else v)
                  for k, v in values.items()}
        with self.engine.begin() as conn:
            conn.execute(update(option_checks).where(option_checks.c.id == check_id).values(**values))

    def check_claim(self, check_id: str, from_status: str, to_status: str) -> bool:
        """Move a check from one status to another only if nobody else has: True if this call did."""
        with self.engine.begin() as conn:
            done = conn.execute(update(option_checks).where(option_checks.c.id == check_id,
                                                            option_checks.c.status == from_status)
                                .values(status=to_status)).rowcount
        return bool(done)

    def check_get(self, check_id: str) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(option_checks).where(option_checks.c.id == check_id)).first()
        return self._check_row(r) if r else None

    def checks_pending(self, since: datetime) -> list[dict]:
        q = (select(option_checks).where(option_checks.c.status == "pending", option_checks.c.created_at >= since)
             .order_by(option_checks.c.created_at))
        with self.engine.connect() as conn:
            return [self._check_row(r) for r in conn.execute(q)]

    def checks_recent(self, username: str | None = None, limit: int = 50, done_only: bool = True) -> list[dict]:
        q = select(option_checks).order_by(option_checks.c.created_at.desc()).limit(limit)
        if username:
            q = q.where(option_checks.c.username == username)
        if done_only:
            q = q.where(option_checks.c.status == "done")
        with self.engine.connect() as conn:
            return [self._check_row(r) for r in conn.execute(q)]

    def checks_open_paper(self) -> list[dict]:
        q = select(option_checks).where(option_checks.c.paper == 1, option_checks.c.paper_closed_at.is_(None))
        with self.engine.connect() as conn:
            return [self._check_row(r) for r in conn.execute(q)]

    def checks_since(self, since: datetime) -> list[dict]:
        q = select(option_checks).where(option_checks.c.created_at >= since, option_checks.c.status == "done")
        with self.engine.connect() as conn:
            return [self._check_row(r) for r in conn.execute(q)]

    # ── Paper trading desk ───────────────────────────────────────────────────

    def desk_account(self, username: str) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(desk_accounts).where(desk_accounts.c.username == username)).first()
        return self._ist(dict(r._mapping)) if r else None

    def desk_account_save(self, row: dict) -> None:
        self._upsert(desk_accounts, [row], ["username"])

    def desk_order_add(self, row: dict) -> bool:
        """False if an order with this id exists already (settlements and square-offs use fixed ids)."""
        values = {k: (json.dumps(v, separators=(",", ":")) if k == "charges" and v is not None else v)
                  for k, v in row.items()}
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        with self.engine.begin() as conn:
            res = conn.execute(insert(desk_orders).values(**values).on_conflict_do_nothing(index_elements=["id"]))
        return bool(res.rowcount)

    def desk_order_update(self, order_id: str, from_status: tuple[str, ...] | None = None, **values) -> bool:
        """Change an order; with `from_status`, only if it is still in one of those (True if this call did)."""
        if "charges" in values and values["charges"] is not None:
            values["charges"] = json.dumps(values["charges"], separators=(",", ":"))
        q = update(desk_orders).where(desk_orders.c.id == order_id)
        if from_status:
            q = q.where(desk_orders.c.status.in_(from_status))
        with self.engine.begin() as conn:
            return bool(conn.execute(q.values(**values)).rowcount)

    @staticmethod
    def _ist(d: dict) -> dict:
        """SQLite hands back naive datetimes (as written, in IST) and Postgres aware UTC ones: both as IST."""
        from options.core.calendar import IST
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.replace(tzinfo=IST) if v.tzinfo is None else v.astimezone(IST)
        return d

    @staticmethod
    def _desk_row(r) -> dict:
        d = Store._ist(dict(r._mapping))
        try:
            d["charges"] = json.loads(d["charges"]) if d.get("charges") else None
        except ValueError:
            d["charges"] = None
        return d

    def desk_order(self, order_id: str) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(desk_orders).where(desk_orders.c.id == order_id)).first()
        return self._desk_row(r) if r else None

    def desk_orders(self, username: str, epoch: int) -> list[dict]:
        q = (select(desk_orders).where(desk_orders.c.username == username, desk_orders.c.epoch == epoch)
             .order_by(desk_orders.c.created_at, desk_orders.c.id))
        with self.engine.connect() as conn:
            return [self._desk_row(r) for r in conn.execute(q)]

    def desk_orders_current(self) -> list[dict]:
        """Every user's orders in their current account (the recorder's view of the whole desk)."""
        j = desk_orders.join(desk_accounts, (desk_orders.c.username == desk_accounts.c.username)
                             & (desk_orders.c.epoch == desk_accounts.c.epoch))
        q = select(desk_orders).select_from(j).order_by(desk_orders.c.created_at, desk_orders.c.id)
        with self.engine.connect() as conn:
            return [self._desk_row(r) for r in conn.execute(q)]

    def desk_orders_active(self, statuses: tuple[str, ...]) -> list[dict]:
        q = select(desk_orders).where(desk_orders.c.status.in_(statuses)).order_by(desk_orders.c.created_at)
        with self.engine.connect() as conn:
            return [self._desk_row(r) for r in conn.execute(q)]

    def notify(self, channel: str, payload: str) -> None:
        """Postgres NOTIFY (a no-op elsewhere): wakes whoever LISTENs on `channel` at once."""
        if self.engine.dialect.name == "postgresql":
            with self.engine.begin() as conn:
                conn.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": channel, "payload": payload})

    # ── Session metrics ──────────────────────────────────────────────────────

    def metrics_add(self, row: dict) -> None:
        self._upsert(session_metrics, [row], ["ts"])

    def metrics_since(self, since: datetime) -> list[dict]:
        q = select(session_metrics).where(session_metrics.c.ts >= since).order_by(session_metrics.c.ts)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    # ── Audit log ────────────────────────────────────────────────────────────

    def audit(self, actor: str, action: str, detail: str, now: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(audit_log.insert().values(ts=now, actor=actor[:64], action=action[:48], detail=detail[:4000]))

    def audit_recent(self, limit: int = 100) -> list[dict]:
        q = select(audit_log).order_by(audit_log.c.ts.desc(), audit_log.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    # ── Signals ───────────────────────────────────────────────────────────────

    def save_signal(self, sig: Signal, now: datetime) -> None:
        row = {"signal_id": sig.signal_id, "created_at": sig.created_at, "index_name": sig.index,
               "setup": sig.setup, "horizon": sig.horizon, "grade": sig.grade.value, "mode": sig.mode,
               "state": sig.state.value, "data": sig.model_dump_json(), "updated_at": now}
        self._upsert(signals, [row], ["signal_id"])

    def signal_event(self, signal_id: str, kind: str, price: float | None, message: str, now: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(signal_events.insert().values(signal_id=signal_id, ts=now, kind=kind, price=price,
                                                       message=message))

    def _signals(self, q) -> list[Signal]:
        with self.engine.connect() as conn:
            return [Signal.model_validate_json(r.data) for r in conn.execute(q)]

    def open_signals(self) -> list[Signal]:
        q = select(signals.c.data).where(signals.c.state.in_([s.value for s in OPEN_STATES]))
        return self._signals(q.order_by(signals.c.created_at))

    def signals_since(self, since: datetime, until: datetime | None = None) -> list[Signal]:
        q = select(signals.c.data).where(signals.c.created_at >= since)
        if until is not None:
            q = q.where(signals.c.created_at < until)
        return self._signals(q.order_by(signals.c.created_at))

    def get_signal(self, signal_id: str) -> Signal | None:
        found = self._signals(select(signals.c.data).where(signals.c.signal_id == signal_id))
        return found[0] if found else None

    def signal_history(self, signal_id: str) -> list[dict]:
        q = (select(signal_events).where(signal_events.c.signal_id == signal_id)
             .order_by(signal_events.c.ts, signal_events.c.id))
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def count_signals_on(self, start: datetime, end: datetime) -> int:
        q = select(func.count()).select_from(signals).where(signals.c.created_at >= start,
                                                            signals.c.created_at < end)
        with self.engine.connect() as conn:
            return conn.execute(q).scalar() or 0

    # ── Evaluations and board ────────────────────────────────────────────────

    def log_evaluation(self, now: datetime, index: str, setup: str, side: int, grade: str | None,
                       score: float | None, outcome: str, reasons: list[str]) -> None:
        with self.engine.begin() as conn:
            conn.execute(evaluations.insert().values(ts=now, index_name=index, setup=setup, side=side, grade=grade,
                                                     score=score, outcome=outcome, reasons="; ".join(reasons)))

    def signalled_keys_since(self, since: datetime) -> set[tuple[str, str, int]]:
        """(index, setup, side) already decided today: a restarted engine must not send them again."""
        q = (select(evaluations.c.index_name, evaluations.c.setup, evaluations.c.side)
             .where(evaluations.c.ts >= since, evaluations.c.outcome.in_(("SIGNAL", "OVER_BUDGET"))).distinct())
        with self.engine.connect() as conn:
            return {(r.index_name, r.setup, int(r.side)) for r in conn.execute(q)}

    def evaluations_since(self, since: datetime, limit: int = 200) -> list[dict]:
        q = select(evaluations).where(evaluations.c.ts >= since).order_by(evaluations.c.ts.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def save_board(self, index: str, board: dict, now: datetime) -> None:
        self._upsert(board_state, [{"index_name": index, "ts": now, "data": json.dumps(board, default=str)}],
                     ["index_name"])

    def load_board(self, index: str) -> dict | None:
        q = select(board_state.c.data).where(board_state.c.index_name == index)
        with self.engine.connect() as conn:
            raw = conn.execute(q).scalar()
        return json.loads(raw) if raw else None

    def save_agent_status(self, key: str, payload: dict, now: datetime) -> None:
        self._upsert(agent_status, [{"key": key, "ts": now, "data": json.dumps(payload, default=str)}], ["key"])

    def load_agent_status(self, key: str) -> dict | None:
        q = select(agent_status.c.data).where(agent_status.c.key == key)
        with self.engine.connect() as conn:
            raw = conn.execute(q).scalar()
        return json.loads(raw) if raw else None
