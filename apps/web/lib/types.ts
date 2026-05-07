import type { Band } from "@/stores/regime-store";

export type { Band };

export type OnboardingStep =
  | "connect"
  | "risk"
  | "universe"
  | "activate"
  | "done";

export interface OnboardingStatus {
  activated: boolean;
  step: OnboardingStep;
}

export interface PulseResponse {
  nav: number;
  nav_change_pct: number;
  attention_score: number;
  attention_band: Band;
  pending_decisions_count: number;
  recent_actions: Array<{
    action: string;
    rationale: string;
    timestamp: string;
  }>;
  positions_summary: Array<{ ticker: string; market_value: number }>;
}

export interface RegimeResponse {
  a_t: number;
  band: Band;
  z_t_posterior: number[];
  ood_score: number;
  changepoint_probability: number;
}

export interface AttentionResponse {
  a_t: number;
  band: Band;
  decision_seconds_today: number;
  fatigue_signal: boolean;
}

export interface DecisionSummary {
  id: string;
  decision_type: string;
  instruments: string;
  action: string;
  confidence: number;
  dollar_impact: number;
  created_at_day: string;
}

export interface DecisionDetail {
  id: string;
  decision_type: string;
  instruments: string;
  action: string;
  confidence: number;
  status: string;
  rationale: string;
}

export interface BriefResponse {
  decision_id: string;
  dollar_impact: number;
  card: {
    action_line: string;
    counter_evidence: string;
    what_would_change_mind: string;
    buttons: string[];
  };
  sections: Array<{
    title: string;
    content: string;
    type: string;
  }>;
}

export interface PortfolioResponse {
  nav: number;
  cash: number;
  positions_count: number;
  total_value: number;
}

export interface Position {
  ticker: string;
  quantity: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight: number;
  drift_from_target: number;
}

export interface AllocationResponse {
  allocations: Array<{
    category: string;
    weight: number;
    target_weight: number;
    drift: number;
  }>;
}

export interface AttributionResponse {
  total_return: number;
  factors: Array<{
    name: string;
    contribution: number;
  }>;
}

export interface RiskMetrics {
  portfolio_var_95: number;
  portfolio_var_99: number;
  max_drawdown: number;
  sharpe_ratio: number;
  volatility: number;
}

export interface BacktestRun {
  id: string;
  name: string;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface BacktestResult {
  run_id: string;
  cagr: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  calmar: number | null;
  turnover: number | null;
  win_rate: number | null;
  equity_curve: Array<{ date: string; value: number }>;
  regime_breakdown?: Array<{
    name: string;
    return_pct: number;
    sharpe: number | null;
    time_pct: number;
  }>;
  sub_horizons?: Array<{
    label: string;
    return: number | null;
    periods: number;
  }>;
}

export interface BacktestRegimeBreakdown {
  run_id: string;
  regimes: Array<{
    name: string;
    return_pct: number;
    sharpe: number | null;
    time_pct: number;
  }>;
}

export interface BacktestConsistency {
  run_id: string;
  monthly: {
    positive_periods: number;
    total_periods: number;
    positive_fraction: number;
  };
  quarterly: {
    positive_periods: number;
    total_periods: number;
    positive_fraction: number;
  };
}

export interface Signal {
  id: string;
  source: string;
  signal_type: string;
  instrument: string;
  direction: string;
  strength: number;
  timestamp: string;
}

export interface EnvelopeConfig {
  vol_target_low: number;
  vol_target_high: number;
  drawdown_ceiling: number;
  concentration_cap: number;
  cost_budget_ceiling?: number;
  universe_exclusions?: string[];
}

export interface AutonomyState {
  level: number;
  level_name: string;
  can_auto_approve: boolean;
  requires_reauth: boolean;
  level_history?: Array<{
    from_level: number;
    to_level: number;
    changed_at: string;
  }>;
  pending_upgrade?: {
    operating_history: {
      days_at_level: number;
      total_decisions: number;
      override_rate: number;
    };
    brinson_snapshot: Record<string, number>;
    calibration_snapshot: Record<string, unknown>;
    override_log: Array<{
      decision_id: string;
      reason: string;
      timestamp: string;
    }>;
    changes_at_new_level: string[];
  };
}

export interface KillSwitchState {
  isActive: boolean;
  reason: string | null;
  activated_at: string | null;
  confirmation_code?: string | null;
  state_brief?: Record<string, unknown>;
}

export interface DataSourceStatus {
  name: string;
  status: string;
  last_update: string | null;
}

export interface PaperLiveState {
  mode: "paper" | "live";
  paper_start_date: string | null;
  live_start_date: string | null;
  days_in_paper: number;
}

export interface ComplianceRule {
  id: string;
  name: string;
  severity: string;
  status: string;
  description: string;
}

export interface DebateThread {
  thread_id: string;
  decision_id?: string;
  status: string;
  originating_context?: string;
  last_activity?: string;
}

export interface DebateMessage {
  id: string;
  content: string;
  severity: string;
  role: "user" | "agent";
  provenance_pointers?: Array<{
    source: string;
    reference: string;
    snippet?: string;
  }>;
}

/** Multi-turn debate turn record (stored in debate_threads fabric table) */
export interface DebateTurn {
  turn_number: number;
  user_message: string;
  response: DebateTurnResponse;
  portfolio_context_snapshot: DebatePortfolioContext;
  provenance_pointers: DebateProvenancePointer[];
  timestamp: string;
}

export interface DebateTurnResponse {
  recommendation: string;
  steel_man: string;
  red_team: string;
  concession_count: number;
  final_confidence: number;
  resolution_state: "updated" | "maintained" | "open" | "envelope_change";
  rounds?: number;
  parse_error?: boolean;
  raw_content_preview?: string;
}

export interface DebatePortfolioContext {
  nav?: number;
  positions_count?: number;
  positions: DebatePosition[];
  weights: Record<string, number>;
  relevant_positions?: DebatePosition[];
  regime: DebateRegimeState;
}

export interface DebatePosition {
  ticker: string;
  market_value: number;
  unrealized_pnl: number;
  quantity: number;
  avg_cost: number;
  weight: number;
}

export interface DebateRegimeState {
  z_scale: number;
  ood_score: number;
  z_dim?: number;
  period_end?: string;
}

export interface DebateProvenancePointer {
  source: string;
  reference: string;
  snippet?: string;
}

/** Full multi-turn debate thread from the debate_threads fabric table */
export interface MultiTurnDebateThread {
  thread_id: string;
  decision_id: string;
  status: string;
  turns: DebateTurn[];
  portfolio_context: DebatePortfolioContext;
  created_at: string;
}

/** Result of adding a turn to a multi-turn debate thread */
export interface DebateTurnResult {
  thread_id: string;
  turn_number: number;
  response: DebateTurnResponse;
  turns: DebateTurn[];
  portfolio_context: DebatePortfolioContext;
  provenance_pointers: DebateProvenancePointer[];
  status: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  severity: string;
  details: string;
  filed_at: string;
}

export interface BriefSummary {
  id: string;
  title: string;
  hypothesis: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BriefDetail {
  id: string;
  title: string;
  hypothesis: string;
  constraints: string;
  regime_assumptions: string;
  metrics: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface BriefVersion {
  version: number;
  title: string;
  hypothesis: string;
  constraints: string;
  regime_assumptions: string;
  metrics: string;
  status: string;
  created_at: string;
}

// Notification types (specs/09 S7)
export type NotificationTier =
  | "silent_in_app"
  | "standard_push"
  | "prominent_push_haptic"
  | "emergency";

export interface NotificationPreferences {
  tiers: Record<string, NotificationTier>;
  quiet_hours: {
    start: string;
    end: string;
    timezone: string;
  };
  daily_attention_ceiling_minutes: number;
}

export interface AttentionReport {
  decision_seconds_this_week: number;
  decision_count: number;
  average_time_to_decide: number;
  notification_volume_by_tier: Record<string, number>;
  fatigue_signal_present: boolean;
  override_rate: number;
}
