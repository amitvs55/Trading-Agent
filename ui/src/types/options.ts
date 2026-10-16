// Types for the live index-options signal tool (mirrors options/core/schemas.py and api/routes/options.py)

export type Status = "pass" | "warn" | "fail" | "na";
export type SignalState = "TRIGGERED" | "ACTIVE" | "T1_HIT" | "CLOSED" | "EXPIRED" | "CANCELLED";

export interface PillarCheck {
  pillar: string;
  status: Status;
  detail: string;
}

export interface Contract {
  index: string;
  tradingsymbol: string;
  token: number;
  expiry: string;
  strike: number;
  right: "CE" | "PE";
  lot_size: number;
}

export interface Signal {
  signal_id: string;
  created_at: string;
  index: string;
  setup: string;
  horizon: "intraday" | "positional";
  action: "BUY_CE" | "BUY_PE";
  grade: "A" | "B" | "C";
  score: number;
  contract: Contract;
  entry_low: number;
  entry_high: number;
  stop_loss: number;
  invalidation: number;
  invalidation_rule: string;
  t1: number;
  t2: number;
  valid_until: string;
  time_stop: string | null;
  exit_by: string | null;
  lots: number;
  risk_rupees: number;
  over_budget: boolean;
  checks: PillarCheck[];
  rationale: string[];
  mode: "SHADOW" | "LIVE";
  state: SignalState;
  fill_price: number | null;
  filled_at: string | null;
  initial_stop: number | null;
  booked_t1: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  closed_at: string | null;
  pnl_rupees: number | null;
  r_multiple: number | null;
}

export interface Quote {
  ts: string;
  ltp: number | null;
  bid: number | null;
  ask: number | null;
}

export interface SignalsResponse {
  signals: Signal[];
  quotes: Record<string, Quote>;
  setup_labels: Record<string, string>;
}

export interface SignalEvent {
  id: number;
  signal_id: string;
  ts: string;
  kind: string;
  price: number | null;
  message: string;
}

export interface SignalDetail {
  signal: Signal;
  events: SignalEvent[];
  setup_label: string;
}

export interface BoardPillar {
  pillar: string;
  bias: number;
  strength: number;
  status: Status | null;
  detail: string;
}

export interface Board {
  index: string;
  as_of: string;
  spot: number | null;
  fut: number | null;
  basis: number;
  vix: number | null;
  vix_pct: number | null;
  atm_iv: number | null;
  expected_move_1d: number | null;
  regime: string;
  phase: string;
  htf_trend: string;
  expiry_day: boolean;
  monthly_expiry: boolean;
  nearest_expiry: string | null;
  lot_size: number;
  strike_step: number;
  levels: Record<string, number>;
  oi: Record<string, number>;
  pillars: BoardPillar[];
}

export interface BoardResponse {
  boards: Record<string, Board>;
  now_ist: string;
}

export interface OptionsStatus {
  now_ist: string;
  trading_day: boolean;
  next_trading_day: string;
  session_phase: string;
  indices: string[];
  data_provider: "angel" | "kite";
  data_provider_name: string;
  data_configured: boolean;
  data_connected_today: boolean;
  data_needs_manual_login: boolean;
  kite_configured: boolean;
  telegram_configured: boolean;
  kite_connected_today: boolean;
  bars_today: number;
  last_bar_at: string | null;
  risk: { capital: number; risk_per_trade_pct: number; daily_loss_stop_pct: number };
}

export interface Stats {
  trades: number;
  wins: number;
  win_rate: number | null;
  avg_r: number | null;
  expectancy_rupees: number | null;
  total_rupees: number;
  max_drawdown_rupees: number;
  profit_factor: number | null;
}

export interface Performance {
  overall: Stats;
  by_setup: Record<string, Stats>;
  by_grade: Record<string, Stats>;
  by_mode: Record<string, Stats>;
  by_horizon: Record<string, Stats>;
  equity: { t: string; equity: number; pnl: number; id: string; mode: string }[];
  r_values: number[];
  counts: { signals: number; traded: number; expired: number; cancelled: number };
  setup_labels: Record<string, string>;
  capital: number;
}

export interface Evaluation {
  id: number;
  ts: string;
  index_name: string;
  setup: string;
  side: number;
  grade: string | null;
  score: number | null;
  outcome: "SIGNAL" | "NO_TRADE" | "GRADE_C" | "OVER_BUDGET";
  reasons: string;
}

export interface EvaluationsResponse {
  evaluations: Evaluation[];
  setup_labels: Record<string, string>;
}
