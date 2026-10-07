/**
 * GoldenMinutes API Client
 * Centralized client connecting the React UI to the FastAPI backend.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';
const CUSTOMER_KEY = import.meta.env.VITE_CUSTOMER_KEY || 'demo_customer_secret_key';
const ANALYST_KEY = import.meta.env.VITE_ANALYST_KEY || 'demo_analyst_secret_key';

let isStubDetected = true; // default true for P0 until proven otherwise
const stubListeners: Set<(isStub: boolean) => void> = new Set();

export function onStubStatusChange(listener: (isStub: boolean) => void): () => void {
  stubListeners.add(listener);
  listener(isStubDetected);
  return () => stubListeners.delete(listener);
}

function updateStubStatus(response: Response) {
  const stubHeader = response.headers.get('x-gm-stub');
  const isStub = stubHeader === '1';
  if (isStub !== isStubDetected) {
    isStubDetected = isStub;
    stubListeners.forEach(listener => listener(isStubDetected));
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  role: 'customer' | 'analyst' = 'customer'
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const apiKey = role === 'analyst' ? ANALYST_KEY : CUSTOMER_KEY;

  const headers = new Headers(options.headers || {});
  headers.set('Content-Type', 'application/json');
  headers.set('X-API-Key', apiKey);

  const response = await fetch(url, {
    ...options,
    headers,
  });

  updateStubStatus(response);

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson?.error?.message || errorDetail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export interface ScorePayload {
  txn_id: string;
  type: string;
  sender_wallet_id: string;
  recipient_wallet_id: string;
  amount_bdt: number;
  channel: string;
  device_id: string;
  balance_before: number;
}

export interface ReasonCode {
  code: string;
  weight: number;
}

export interface ScoreResult {
  txn_id: string;
  risk_score: number;
  action: 'allow' | 'warn' | 'verify' | 'hold';
  reason_codes: ReasonCode[];
  customer_message: { bn: string; en: string };
  alert_id?: string;
  model_version: string;
  policy_version: string;
  latency_ms: number;
}

export interface AlertSummary {
  alert_id: string;
  decision_id: string;
  txn_id: string;
  status: 'open' | 'in_review' | 'resolved' | 'late';
  priority: number;
  money_at_risk: number;
  deadline_ts: string;
  created_at: string;
  sender_wallet_id: string;
  recipient_wallet_id: string;
  amount_bdt: number;
}

export interface AlertDetail extends AlertSummary {
  risk_score: number;
  action: 'allow' | 'warn' | 'verify' | 'hold';
  reason_codes: ReasonCode[];
  narrative?: { bn: string; en: string };
  evidence?: Record<string, any>;
  actions_taken: any[];
}

export interface AblationRow {
  variant: string;
  name?: string;
  status?: string;
  pr_auc?: number | null;
  ffr?: number | null;
  value_weighted_recall?: number | null;
  recall_at_1pct_ffr?: number | null;
  brier_score?: number | null;
  ece?: number | null;
  p95_latency_ms?: number | null;
  latency_p95_ms?: number | null;
  typology_recalls?: Record<string, number>;
}

export interface CiStat {
  mean: number;
  ci_lower: number;
  ci_upper: number;
}

export interface LiftSummary {
  profile?: string;
  n_bootstraps?: number;
  pr_auc_deltas: Record<string, CiStat | undefined>;
  rewiring_test?: {
    baseline_pr_auc: number;
    rewired_pr_auc: number;
    drop_under_rewiring: number;
    topology_dependency_verified: boolean;
  };
  max_single_feature?: { feature?: string; roc_auc?: number };
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'customer' | 'wallet' | 'agent' | 'merchant' | 'device';
  risk_score?: number | null;
  is_mule?: boolean | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  amount_bdt: number;
  ts?: string | null;
  txn_count: number;
}

export interface GraphResponse {
  wallet_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SimulateAttackStep {
  step: number;
  title?: string;
  sender_wallet_id?: string;
  recipient_wallet_id?: string;
  amount_bdt?: number;
  action?: 'allow' | 'warn' | 'verify' | 'hold';
  risk_score?: number;
  alert_id?: string | null;
  description: string;
  description_bn?: string;
}

export interface SimulateAttackResult {
  status: string;
  scenario_id: string;
  message: string;
  steps: SimulateAttackStep[];
}

export interface MetricsData {
  fraud_value_intercepted_bdt: number;
  false_friction_rate: number;
  median_decision_time_ms: number;
  p95_decision_time_ms: number;
  ablation_table: AblationRow[];
  held_out_typology_recall?: number;
  fairness_slices?: Record<string, Record<string, any>>;
  sensitivity_grid?: Array<{
    effectiveness_scenario: string;
    hold_eff: number;
    verify_eff: number;
    intercepted_bdt: number;
  }>;
  hold_resolution_minutes?: number | null;
  total_scored: number;
  total_alerts: number;
  champion_variant?: string | null;
  primary_population?: string[] | null;
  lift_summary?: LiftSummary | null;
}

export interface DemoAccount {
  wallet_id: string;
  customer_id: string;
  name: string;
  balance_bdt: number;
  persona: string;
  description: string;
}

export const api = {
  checkHealth: () => request<{ status: string; environment: string }>('/health'),
  scoreTransaction: (data: ScorePayload) => request<ScoreResult>('/v1/score', { method: 'POST', body: JSON.stringify(data) }, 'customer'),
  getAlerts: (statusFilter?: string) => {
    const query = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : '';
    return request<{ alerts: AlertSummary[]; total: number }>(`/v1/alerts${query}`, {}, 'analyst');
  },
  getAlertDetail: (alertId: string) => request<AlertDetail>(`/v1/alerts/${alertId}`, {}, 'analyst'),
  decideAlert: (alertId: string, action: 'approve' | 'release' | 'escalate', note?: string) =>
    request(`/v1/alerts/${alertId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ action, note })
    }, 'analyst'),
  getWalletGraph: (walletId: string) => request<GraphResponse>(`/v1/graph/${encodeURIComponent(walletId)}`, {}, 'analyst'),
  recordFeedback: (data: { decision_id: string; source: 'customer' | 'analyst'; label: 'this_was_me' | 'not_me' | 'fraud' | 'legit' }) =>
    request<{ feedback_id: string; status: string }>('/v1/feedback', { method: 'POST', body: JSON.stringify(data) }, 'customer'),
  getMetrics: () => request<MetricsData>('/v1/metrics', {}, 'analyst'),
  getDemoAccounts: () => request<{ senders: DemoAccount[]; recipients: DemoAccount[] }>('/v1/demo/accounts', {}, 'customer'),
  simulateAttack: (scenario_id?: string) =>
    request<SimulateAttackResult>('/v1/simulate/attack', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenario_id || 'impersonation_scam_01' })
    }, 'customer'),
  simulateReset: () => request<{ status: string; message: string }>('/v1/simulate/reset', { method: 'POST' }, 'customer'),
};
