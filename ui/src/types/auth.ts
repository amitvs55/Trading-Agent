// Accounts and the admin Connectors API (api/routes/admin.py)

export interface User {
  id: number;
  username: string;
  role: "admin" | "viewer" | string;
  full_name?: string | null;
  disabled?: boolean;
  created_at?: string;
  last_login_at?: string | null;
}

export interface UsersResponse {
  users: User[];
  roles: string[];
}

export interface SessionResponse {
  token: string;
  user: User;
}

export type CheckStatus = "ok" | "warn" | "fail" | "skip";

export interface HealthResult {
  id?: string;
  name?: string;
  status: CheckStatus;
  message: string;
  details: Record<string, unknown>;
  latency_ms: number | null;
  checked_at: string;
}

export interface ConnectorField {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
  placeholder: string;
  source: "app" | "env" | "unset";
  is_set: boolean;
  display: string;
  problem: string | null;       // why the current value looks wrong (format check), if it does
  updated_at: string | null;
}

export interface Connector {
  id: "angel" | "kite" | "telegram" | "email" | "openai";
  name: string;
  role: string;
  description: string;
  docs_url: string;
  fields: ConnectorField[];
  configured: boolean;
  missing: string[];
  health: HealthResult | null;
}

export interface RecorderStatus {
  ts: string;
  state: "running" | "waiting" | "restarting";
  next_start: string | null;        // or, while restarting, when the restart happens
  session_started_at: string | null;
  last_exit_code: number | null;
  last_command: string | null;
  restarts_today?: number;
  gave_up?: boolean;                // stopped too often today: no more automatic restarts
}

export interface TradingSettings {
  capital: number;
  risk_per_trade_pct: number;
  daily_loss_stop_pct: number;
  live_setups: string[];
  bars_retention_days: number;
  setups: Record<string, string>;
  limits: Record<string, [number, number]>;
}

export interface ConnectorsResponse {
  connectors: Connector[];
  data_provider: "angel" | "kite";
  providers: Record<string, string>;
  trading: TradingSettings;
  recorder: RecorderStatus | null;
  secret_key_from_env: boolean;
}

/** PUT /api/admin/connectors/{id}: the new state plus the test the edits had to pass first. */
export interface SaveConnectorResponse extends ConnectorsResponse {
  test: HealthResult | null;
  missing: string[];
}

export interface HealthResponse {
  results: Record<string, HealthResult>;
  checks: Record<string, string>;
  recorder: RecorderStatus | null;
}

// ── Operations page (api/routes/admin.py) ────────────────────────────────────

export interface ControlsState {
  paused: boolean;
  paused_by?: string | null;
  paused_at?: string | null;
  reason?: string | null;
  exit_all_at?: string | null;
  exit_all_by?: string | null;
  exit_all_pending: string | null;   // a request the engine hasn't carried out yet
}

export type AlertStatus = "pending" | "sent" | "failed" | "expired";

export interface AlertRow {
  id: number;
  created_at: string;
  text: string;
  status: AlertStatus;
  channel: string | null;
  attempts: number;
  last_error: string | null;
  sent_at: string | null;
}

export interface AlertsResponse {
  alerts: AlertRow[];
  last_24h: Partial<Record<AlertStatus, number>>;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  detail: string | null;
}

export interface RecorderEvent {
  id: number;
  ts: string;
  kind: string;
  detail: string | null;
}

export interface MetricsResponse {
  rows: { ts: string; ticks: number; bars: number; rejected_ticks: number; eval_ms: number | null;
          alert_delay_s: number | null; open_signals: number | null; live_lag_ms?: number | null }[];
  summary: { minutes: number; ticks_per_min_last: number | null; rejected_ticks: number;
             eval_ms: { p95: number; max: number } | null; alert_delay_s: { p95: number; max: number } | null;
             live_lag_ms?: { p95: number; max: number } | null };
}

export interface Holiday {
  date: string;
  name: string | null;
  source: "built-in" | "added";
}

export interface MarketEvent {
  id: string | null;
  name: string;
  at: string;
  impact: "high" | "medium";
  source: "built-in" | "added";
}

export interface CalendarResponse {
  holidays: Holiday[];
  years: { year: number; complete: boolean; built_in: boolean; count: number }[];
  events: MarketEvent[];
  warning: string | null;
}

// Replays of recorded days with today's rules (api/routes/admin.py, options/backtest/replay_job.py)
export interface ReplayStats {
  trades: number; wins: number; win_rate: number | null; avg_r: number | null; expectancy_rupees: number | null;
  total_rupees: number; max_drawdown_rupees: number; profit_factor: number | null;
}

export interface ReplaySignal {
  id: string; created_at: string; setup: string; horizon: string; action: "BUY_CE" | "BUY_PE"; grade: string;
  score: number; symbol: string; entry_high: number; stop: number; t1: number; t2: number; fill: number | null;
  exit: number | null; exit_reason: string | null; state: string; pnl: number | null; r: number | null;
  over_budget: boolean; risk: number;
}

export interface ReplayReport {
  status: "none" | "queued" | "running" | "done" | "error" | "stopped";
  request?: { from: string; to: string; by: string; requested_at: string; days: number };
  started_at?: string; finished_at?: string; updated_at?: string;
  done?: number; total?: number | null; current?: string | null; stalled?: boolean;
  days?: string[]; signals?: ReplaySignal[]; overall?: ReplayStats; by_setup?: Record<string, ReplayStats>;
  decisions?: { candidates: number; by_outcome: Record<string, number>; reasons: [string, number][] };
  rules?: { risk_per_trade_pct: number; capital: number; indices: string[] };
  notes?: string[]; error?: string; setup_labels?: Record<string, string>;
}

export interface ReplayView {
  report: ReplayReport;
  recorded: { first: string | null; last: string | null; days: number };
  session_running: boolean;
}
