import type { PillarCheck } from "./options";

export interface CheckContractRef {
  symbol: string;
  token: number;
  expiry: string;
  strike: number;
  right: "CE" | "PE";
  lot_size: number;
  label: string;
}

export interface ResolveResponse {
  ok: boolean;
  problem: string | null;
  contract: CheckContractRef | null;
  suggestions: CheckContractRef[];
}

export interface Odds {
  p_profit: number;
  expected: number;
  expected_pct: number | null;
  p10: number;
  p50: number;
  p90: number;
  worst: number;
  best: number;
}

export type PlanOutcome = "stop" | "t1_then_stop" | "t1_then_time" | "t2" | "time";

export interface PlanOdds extends Odds {
  outcomes: Record<PlanOutcome, number>;
  p_t1: number;
}

export interface ViewOdds {
  hold?: Odds;
  plan?: PlanOdds | null;
}

export interface HistoryView extends ViewOdds {
  sessions: number;
  from?: string;
  to?: string;
  note?: string;
  similar?: ViewOdds & { sessions: number; rule: string };
}

export interface CheckFacts {
  source: string;
  as_of: string;
  checked_at: string;
  data_as_of: string | null;
  market_open: boolean;
  phase: string;
  index: string;
  side: 1 | -1;
  horizon: "intraday" | "expiry";
  spot: number | null;
  fut: number | null;
  forward: number | null;
  contract: {
    symbol: string; expiry: string; strike: number; right: "CE" | "PE"; lot_size: number; quote_source: string;
    bid: number | null; ask: number | null; ltp: number | null; mid: number | null; spread_pct: number | null;
    oi: number | null; oi_change_pct: number | null; iv: number | null;
    greeks: { delta: number; gamma: number; vega: number; theta_day: number } | null;
  };
  atm_iv: number | null;
  vix: number | null;
  expiry_day: boolean;
  levels: Record<string, number>;
  candidate: { trigger: number; invalidation: number; note: string; setups_fired: boolean };
  plan: CheckPlan | null;
  score: number | null;
  pillars: PillarCheck[];
  gates: { name: string; ok: boolean; reason: string }[];
  engine_signals: { id: string; state: string; grade: string; mode: string; entry_high: number; stop: number; t1: number; t2: number }[];
}

export interface CheckPlan {
  entry_low?: number;
  entry_high: number;
  stop: number;
  t1: number;
  t2: number;
  rr1: number;
  rr2: number;
}

export interface CheckVerdict {
  call: "Worth taking" | "Marginal" | "Avoid" | "Can't price";
  tone: "good" | "warn" | "bad" | "neutral";
  score: number | null;
  summary: string;
  basis?: string;
  blocks?: string[];
  for: string[];
  against: string[];
}

export interface CheckReport {
  facts: CheckFacts;
  params: { amount: number; entry: number | null; horizon: "intraday" | "expiry"; iv_shift: number; slippage_pct: number;
            capital: number; risk_pct: number };
  priced: boolean;
  position?: {
    entry: number; entry_note: string | null; lots: number; shown_lots: number; units: number; lot_cost: number; capital_used: number; leftover: number;
    min_amount: number | null; buy_charges: number; round_trip_charges: number; max_loss: number; breakeven: number;
    stop_risk: number | null; budget: number; over_budget: boolean; iv_used: number;
  };
  plan?: CheckPlan | null;
  horizon?: { start: string; end: string; label: string; settles: boolean; starts_at_open: boolean };
  market?: ViewOdds & { paths: number; sigma: number };
  history?: HistoryView | null;
  scenarios?: { moments: { label: string; at: string }[]; rows: { spot: number; label: string; move_pct: number;
                cells: { value: number; pnl: number }[] }[]; sd: number };
  curve?: { spot: number; sd: number; points: { x: number; exit: number; expiry: number }[] };
  verdict: CheckVerdict;
  evidence: {
    pillars: PillarCheck[];
    gates: { name: string; ok: boolean; reason: string }[];
    numbers: { label: string; value: string | number }[];
    assumptions: string[];
    data_times: { facts: string; market_data: string | null; source: string };
    history_span: { sessions: number; from: string; to: string } | null;
    why_market_view_loses: string;
  };
}

export interface PaperFollow {
  entry: number | null;
  units: number | null;
  exit: number | null;
  closed_at: string | null;
  symbol: string | null;
  pnl?: number;
  closed_with?: string;
}

export interface CheckOutcome {
  after_30m?: { price: number | null; pnl: number | null };
  at_exit?: { price: number | null; pnl: number | null; at: string };
}

export interface CheckResponse {
  id: string;
  created_at: string;
  query: string;
  report: CheckReport;
  paper?: PaperFollow | null;
  outcome?: CheckOutcome | null;
}

export interface CheckSummary {
  verdict: CheckVerdict["call"];
  tone: CheckVerdict["tone"];
  score: number | null;
  entry: number | null;
  lots: number | null;
  units: number | null;
  capital_used: number | null;
  p_profit: number | null;
  expected: number | null;
  odds_from: string;
  horizon_end: string | null;
  settles: boolean | null;
  market_open: boolean | null;
}

export interface CheckRow {
  id: string;
  created_at: string;
  query: string;
  symbol: string | null;
  token: number | null;
  expiry: string | null;
  username: string | null;
  summary: CheckSummary | null;
  outcome: CheckOutcome | null;
  paper: PaperFollow | null;
}

export interface CheckRecord {
  checks: number;
  scored: number;
  enough: boolean;
  verdicts: { verdict: string; checks: number; made_money_rate: number; avg_pnl_pct: number | null }[];
  calibration: { from: number; to: number; checks: number; said: number; happened: number }[];
}

export interface ChecksResponse {
  checks: CheckRow[];
  record: CheckRecord;
}
