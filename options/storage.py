"""Persistence: Kite sessions, daily instrument snapshots, 1-minute bars and session events.

Postgres on Railway, SQLite locally and in tests. Kite drops expired contracts from its
instrument dump, so the daily snapshot is what lets old bars be mapped back to strikes.
"""

from datetime import date, datetime
from pathlib import Path

import json

from sqlalchemy import (BigInteger, Column, Date, DateTime, Float, Integer, MetaData, String,
                        Table, Text, create_engine, func, select)
from sqlalchemy.engine import Engine

from options.core.schemas import OPEN_STATES, Signal
from options.reference import as_date

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
    return engine


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
