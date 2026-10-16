// Accounts and the admin Connectors API (api/routes/admin.py)

export interface User {
  id: number;
  username: string;
  role: "admin" | string;
  created_at?: string;
  last_login_at?: string | null;
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
  id: "angel" | "kite" | "telegram" | "openai";
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
  state: "running" | "waiting";
  next_start: string | null;
  session_started_at: string | null;
  last_exit_code: number | null;
  last_command: string | null;
}

export interface TradingSettings {
  capital: number;
  risk_per_trade_pct: number;
  daily_loss_stop_pct: number;
  live_setups: string[];
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
