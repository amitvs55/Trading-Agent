"""Shared types for pillars and signals (plan §9)."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel

Status = Literal["pass", "warn", "fail", "na"]
STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "na": "➖"}


class Action(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class SignalState(str, Enum):
    TRIGGERED = "TRIGGERED"      # sent, waiting for the entry price
    ACTIVE = "ACTIVE"            # entry assumed filled at the ask
    T1_HIT = "T1_HIT"            # T1 reached: half booked (2+ lots) or gain locked in (1 lot)
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"          # entry never reached inside the validity window
    CANCELLED = "CANCELLED"      # invalidated before entry


OPEN_STATES = {SignalState.TRIGGERED, SignalState.ACTIVE, SignalState.T1_HIT}


class PillarCheck(BaseModel):
    pillar: str
    status: Status
    detail: str


@dataclass
class PillarView:
    """One analysis pillar's reading. Directional pillars set `bias` (+1 bull, −1 bear,
    0 neutral) and `strength`; non-directional ones set `status` directly."""
    pillar: str
    detail: str
    bias: int = 0
    strength: float = 0.0
    status: Status | None = None
    features: dict = field(default_factory=dict)

    def check_for(self, side: int) -> PillarCheck:
        if self.status is not None:
            status = self.status
        elif self.bias == 0:
            status = "warn"
        elif self.bias == side:
            status = "pass" if self.strength >= 0.5 else "warn"
        else:
            status = "fail" if self.strength >= 0.3 else "warn"
        return PillarCheck(pillar=self.pillar, status=status, detail=self.detail)


class Contract(BaseModel):
    index: str
    tradingsymbol: str
    token: int
    expiry: date
    strike: float
    right: Literal["CE", "PE"]
    lot_size: int


class Signal(BaseModel):
    signal_id: str                      # NF-261016-003
    created_at: datetime                # stored before any outcome; never edited
    index: str
    setup: str
    horizon: Literal["intraday", "positional"]
    action: Action
    grade: Grade
    score: float
    contract: Contract
    entry_low: float
    entry_high: float
    stop_loss: float                    # premium
    invalidation: float                 # underlying level; a close beyond it exits
    invalidation_rule: str              # e.g. "NIFTY fut 5m close below 24,560"
    invalidation_tf: Literal["5min", "day"] = "5min"
    underlying_token: int = 0           # instrument whose close is checked against invalidation
    exit_by: date | None = None         # positional: last day to hold
    t1: float
    t2: float
    valid_until: datetime
    time_stop: time | None
    lots: int
    risk_rupees: float
    over_budget: bool = False
    checks: list[PillarCheck]
    rationale: list[str] = []
    mode: Literal["SHADOW", "LIVE"] = "SHADOW"
    state: SignalState = SignalState.TRIGGERED
    fill_price: float | None = None
    filled_at: datetime | None = None
    initial_stop: float | None = None
    booked_t1: float | None = None      # price of the partial exit (only when lots >= 2)
    peak_bid: float | None = None       # highest bid since T1, for the trailing stop
    exit_price: float | None = None
    exit_reason: str | None = None
    closed_at: datetime | None = None
    pnl_rupees: float | None = None     # after all charges, for the suggested lots
    r_multiple: float | None = None

    @property
    def side(self) -> int:
        return 1 if self.action is Action.BUY_CE else -1
