export interface Tx {
  transaction_id: string;
  batch_id: string;
  sequence_number?: number;
  payload: {
    step?: number;
    type?: string;
    amount?: number;
    nameOrig?: string;
    oldbalanceOrg?: number;
    newbalanceOrig?: number;
    nameDest?: string;
    oldbalanceDest?: number;
    newbalanceDest?: number;
    isFraud?: number;
    isFlaggedFraud?: number;
    [key: string]: any;
  };
  generated_at: string;
  kafka_status: string;
  kafka_partition?: number;
  kafka_offset?: number;
  processing_status: string;
  risk_level?: 'L1' | 'L2' | 'L3' | 'L4' | 'L5' | string;
  anomaly_score?: number;
  xgboost_probability?: number;
  xgboost_prediction?: number;
  final_prediction?: number;
  decision_path?: string;
  final_decision?: string;
  alert_id?: string;
  investigation_id?: string;
  investigation_status: 'NOT_APPLICABLE' | 'PENDING' | 'COMPLETED' | 'PARTIAL' | 'INSUFFICIENT_EVIDENCE' | 'FAILED' | string;
  investigation?: {
    investigation_summary?: string;
    alert_assessment?: string;
    evidence?: any[];
    risk_factors?: string[];
    counter_evidence?: string[];
    missing_evidence?: string[];
    historical_comparison?: any;
    recommended_review_points?: string[];
    [key: string]: any;
  };
  updated_at?: string;
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Service {
  status: string;
  available: boolean;
  detail?: string;
  version?: string;
  latency_ms?: number;
}

export interface Batch {
  batch_id: string;
  idempotency_key?: string;
  request_hash?: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'CANCELLED' | 'FAILED' | string;
  requested_count: number;
  generated_count: number;
  sent_count: number;
  failed_count: number;
  processed: number;
  fraud_alerts: number;
  low_risk: number;
  investigation_requests?: number;
  investigations_succeeded?: number;
  investigations_partial?: number;
  investigations_pending?: number;
  investigations_failed?: number;
  delay: number;
  source: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  progress?: number;
  error_message?: string;
}

export interface ActivityEvent {
  event_id: number;
  batch_id: string;
  created_at: string;
  event_type: string;
  transaction_id?: string;
  message: string;
  data?: Record<string, any> | string;
}

export interface DashboardSummary {
  requested?: number;
  generated: number;
  sent?: number;
  failed?: number;
  processed: number;
  fraud_alerts: number;
  low_risk: number;
  investigations: number;
  investigation_pending: number;
  investigation_success: number;
  investigation_failed: number;
}

export interface DashboardData {
  summary: DashboardSummary;
  current_batch?: Batch | null;
  recent_batches: Batch[];
  recent_transactions: Tx[];
  recent_activity: ActivityEvent[];
}

export interface SystemStatus {
  status: string;
  timestamp: string;
  services: Record<string, Service>;
  summary: {
    total: number;
    available: number;
    degraded: number;
    unavailable: number;
  };
}

export interface LlmStatus {
  provider: string;
  model: string;
  status: string;
  available: boolean | null;
  fallback?: string | null;
  rag_enabled: boolean;
  detail?: string;
}

export interface ChatEvidence {
  source_type: string;
  source_id: string;
  content: any;
  source?: string;
}

export interface ChatResult {
  conversation_id: string;
  answer: string;
  transaction_id?: string | null;
  evidence: ChatEvidence[];
  retrieval_count: number;
  missing_evidence: string[];
  uncertainties: string[];
  llm_provider: string;
  llm_model: string;
}
