// TypeScript types mirroring models/schemas.py Pydantic models

export type TrendSignal = "bullish" | "bearish" | "neutral";
export type NewsImpact  = "very_positive" | "positive" | "neutral" | "negative" | "very_negative";
export type TradeDirection = "long" | "short" | "hold";
export type RiskProfile = "aggressive" | "neutral" | "conservative";
export type FinalAction = "execute" | "hold" | "reject";
export type ExecutionStatus = "executed_simulated" | "held" | "rejected";
export type HealthScore = "strong" | "moderate" | "weak";
export type DebateRecommendation = "strong_buy" | "buy" | "hold" | "sell" | "strong_sell";
export type DebateWinner = "bull" | "bear" | "neutral";

export interface TechnicalIndicators {
  rsi_14:            number | null;
  macd_line:         number | null;
  macd_signal:       number | null;
  macd_histogram:    number | null;
  bollinger_upper:   number | null;
  bollinger_middle:  number | null;
  bollinger_lower:   number | null;
  sma_20:            number | null;
  sma_50:            number | null;
  ema_12:            number | null;
  ema_26:            number | null;
}

export interface MarketDataOutput {
  agent_name:            string;
  ticker:                string;
  timestamp:             string;
  current_price:         number;
  price_change_pct_1d:   number | null;
  price_change_pct_5d:   number | null;
  volume:                number | null;
  avg_volume_10d:        number | null;
  fifty_two_week_high:   number | null;
  fifty_two_week_low:    number | null;
  indicators:            TechnicalIndicators;
  trend_signal:          TrendSignal;
  summary:               string;
}

export interface SentimentOutput {
  agent_name:    string;
  ticker:        string;
  timestamp:     string;
  overall_score: number;
  twitter_score: number | null;
  reddit_score:  number | null;
  sample_posts:  string[];
  data_source:   string;
  summary:       string;
}

export interface NewsItem {
  headline:        string;
  source:          string;
  impact:          NewsImpact;
  relevance_score: number;
}

export interface NewsOutput {
  agent_name:     string;
  ticker:         string;
  timestamp:      string;
  articles:       NewsItem[];
  overall_impact: NewsImpact;
  summary:        string;
}

export interface FundamentalsOutput {
  agent_name:       string;
  ticker:           string;
  timestamp:        string;
  market_cap:       number | null;
  pe_ratio:         number | null;
  forward_pe:       number | null;
  eps:              number | null;
  revenue_growth:   number | null;
  profit_margin:    number | null;
  debt_to_equity:   number | null;
  insider_buy_pct:  number | null;
  sector:           string | null;
  business_summary: string | null;
  health_score:     HealthScore;
  summary:          string;
}

export interface ResearchOutput {
  agent_name:      string;
  ticker:          string;
  timestamp:       string;
  thesis:          string;
  key_arguments:   string[];
  confidence:      number;
  supporting_data: Record<string, unknown>;
}

export interface DebateVerdict {
  agent_name:               string;
  ticker:                   string;
  timestamp:                string;
  winner:                   DebateWinner;
  bull_score:               number;
  bear_score:               number;
  key_consensus_points:     string[];
  key_disagreement_points:  string[];
  final_recommendation:     DebateRecommendation;
  rationale:                string;
}

export interface TradeProposal {
  agent_name:         string;
  ticker:             string;
  timestamp:          string;
  direction:          TradeDirection;
  entry_price:        number | null;
  stop_loss:          number | null;
  take_profit:        number | null;
  position_size_pct:  number;
  risk_reward_ratio:  number | null;
  time_horizon:       string;
  rationale:          string;
}

export interface RiskAssessment {
  agent_name:             string;
  ticker:                 string;
  timestamp:              string;
  profile:                RiskProfile;
  approve:                boolean;
  risk_score:             number;
  max_position_size_pct:  number;
  adjusted_stop_loss:     number | null;
  adjusted_take_profit:   number | null;
  concerns:               string[];
  recommendation:         string;
}

export interface FinalDecision {
  agent_name:              string;
  ticker:                  string;
  timestamp:               string;
  action:                  FinalAction;
  final_entry:             number | null;
  final_stop_loss:         number | null;
  final_take_profit:       number | null;
  final_position_size_pct: number | null;
  reasoning:               string;
  risk_consensus:          string;
}

// LLM token usage / USD cost (mirrors utils/usage.py summary)
export interface UsageBucket {
  calls:             number;
  prompt_tokens:     number;
  completion_tokens: number;
  cached_tokens:     number;
  total_tokens:      number;
  cost_usd:          number;
}

export interface UsageCall {
  agent:             string;
  stage:             number | null;
  model:             string;
  prompt_tokens:     number;
  completion_tokens: number;
  cached_tokens:     number;
  total_tokens:      number;
  cost_usd:          number;
  latency_s:         number;
  is_retry:          boolean;
}

export interface UsageSummary extends UsageBucket {
  model:               string;
  pricing_known:       boolean;
  input_price_per_1m:  number;
  output_price_per_1m: number;
  retries:             number;
  by_agent:            Record<string, UsageBucket>;
  by_stage:            Record<string, UsageBucket>;
  calls_detail:        UsageCall[];
}

export interface UsagePeriod {
  runs:              number;
  calls:             number;
  prompt_tokens:     number;
  completion_tokens: number;
  cached_tokens:     number;
  total_tokens:      number;
  cost_usd:          number;
  avg_cost_per_run:  number;
}

export interface UsageAgentTotal {
  agent:        string;
  calls:        number;
  total_tokens: number;
  cost_usd:     number;
}

export interface UsageReport {
  model:                string;
  all_time:             UsagePeriod;
  today:                UsagePeriod;
  last_7_days:          UsagePeriod;
  daily:                { date: string; cost_usd: number; total_tokens: number; runs: number }[];
  by_agent:             UsageAgentTotal[];
  by_model:             Record<string, UsagePeriod>;
  most_expensive_agent: UsageAgentTotal | null;
  untracked_runs:       number;
}

export interface ExecutionResult {
  agent_name: string;
  ticker:     string;
  timestamp:  string;
  order_id:   string;
  status:     ExecutionStatus;
  details:    string;
  logged_at:  string;
  usage?:     UsageSummary | null;
}

export interface PipelineResult {
  ticker:                string;
  timestamp:             string;
  market_data:           MarketDataOutput;
  sentiment:             SentimentOutput;
  news:                  NewsOutput;
  fundamentals:          FundamentalsOutput;
  bull_case:             ResearchOutput;
  bear_case:             ResearchOutput;
  debate_verdict:        DebateVerdict;
  trade_proposal:        TradeProposal;
  risk_assessments:      RiskAssessment[];
  final_decision:        FinalDecision;
  execution:             ExecutionResult;
  total_duration_seconds: number;
  usage?:                UsageSummary | null;
}

// SSE event types
export interface SSEStageRunning {
  stage:  number;
  status: "running";
  agents: string[];
}
export interface SSEStageComplete {
  stage:   number;
  status:  "complete";
  payload: Record<string, unknown>;
  usage?:  UsageSummary;
}
export interface SSEDone {
  done:        true;
  full_result: PipelineResult;
}
export interface SSEError {
  error: string;
}
export type SSEEvent = SSEStageRunning | SSEStageComplete | SSEDone | SSEError;

// Pipeline UI state
export type PipelineStatus = "idle" | "running" | "done" | "error";

export interface StageData {
  stage1?: { market: MarketDataOutput; sentiment: SentimentOutput; news: NewsOutput; fundamentals: FundamentalsOutput };
  stage2?: { bull_case: ResearchOutput; bear_case: ResearchOutput; debate_verdict: DebateVerdict };
  stage3?: { trade_proposal: TradeProposal };
  stage4?: { risk_assessments: RiskAssessment[] };
  stage5?: { final_decision: FinalDecision };
  stage6?: { execution: ExecutionResult };
}

export interface PipelineState {
  status:       PipelineStatus;
  currentStage: number;
  stages:       StageData;
  fullResult:   PipelineResult | null;
  error:        string | null;
  elapsed:      number;
  usage:        UsageSummary | null;
}

// Price history
export interface Candle {
  date:   string;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}
