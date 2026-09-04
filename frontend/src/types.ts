export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";
export type ReviewDecision = "PENDING" | "CONFIRMED" | "REJECTED";

export interface DashboardMetrics {
  total_work_orders: number;
  unique_assets: number;
  recurring_incidents: number;
  high_risk_assets: number;
  human_review_count: number;
  average_confidence: number;
  repeat_incident_rate: number;
  issue_resolution_rate: number | null;
  mean_time_between_repeats: number | null;
}

export interface DashboardData {
  dataset_label: string;
  metrics: DashboardMetrics;
  incidents_over_time: Array<{ period: string; incidents: number }>;
  issue_distribution: Array<{ name: string; value: number }>;
  high_risk_assets: Array<{ asset_key: string; risk_score: number }>;
  recurrence_trends: Array<{ year: string; total: number; recurring: number }>;
  department_activity: Array<{ department: string; work_orders: number }>;
  patterns: Pattern[];
}

export interface Pattern {
  title: string;
  incident_count: number;
  supporting_work_orders: string[];
}

export interface IncidentSummary {
  incident_id: string;
  asset_key: string;
  issue_family: string;
  department: string;
  first_seen: string;
  last_seen: string;
  work_order_count: number;
  recurring: boolean;
  resolution_status: string;
  confidence: number;
  confidence_level: ConfidenceLevel;
  requires_human_review: boolean;
  risk_score: number;
}

export interface ConfidenceBreakdown {
  semantic_consistency: number;
  asset_consistency: number;
  temporal_consistency: number;
  evidence_strength: number;
  issue_agreement: number;
  conflict_penalty: number;
  score: number;
  level: ConfidenceLevel;
  requires_human_review: boolean;
}

export interface Insight {
  insight_id: string;
  incident_id: string;
  title: string;
  asset_key: string;
  issue_family: string;
  summary: string;
  observations: string[];
  interpretation: string;
  possible_cause: { statement: string; support_level: string };
  recommended_action: string;
  confidence: number;
  confidence_level: ConfidenceLevel;
  requires_human_review: boolean;
  supporting_work_orders: string[];
  contradicting_work_orders: string[];
  confidence_components: ConfidenceBreakdown;
  generated_by: string;
  review_decision?: ReviewDecision;
}

export interface WorkOrderEvidence {
  work_order_id: string;
  date: string;
  category: string;
  department: string;
  status: string;
  priority: string;
  issue_family: string;
  asset_keys: string[];
  comments: Array<{
    redacted_text: string;
    was_redacted: boolean;
    is_meaningful: boolean;
    source_type: string;
  }>;
  match_explanation: { reasons?: string[]; weighted_score?: number; type?: string };
}

export interface IncidentDetail {
  incident: IncidentSummary;
  insight: Insight;
  work_orders: WorkOrderEvidence[];
}

export interface AssetSummary {
  asset_key: string;
  entity_type: string;
  entity_uid: string;
  department: string;
  risk_score: number;
  risk_reasons: string[];
}

export interface AssetDetail {
  asset: AssetSummary & {
    total_work_orders: number;
    recurring_issues: number;
    last_service_date: string | null;
  };
  timeline: Array<{
    work_order_id: string;
    date: string;
    category: string;
    issue_family: string;
    status: string;
    priority: string;
    incident_id: string | null;
    is_repeat: boolean;
  }>;
  incidents: Array<IncidentSummary & { insight: Insight | null }>;
}

export interface ReviewItem {
  review_id: string;
  decision: ReviewDecision;
  reviewer_note: string | null;
  edited_issue_family: string | null;
  edited_recommendation: string | null;
  incident: IncidentSummary;
  insight: Insight;
}

export interface SearchResult {
  query: string;
  interpreted_filters: {
    issue_family: string | null;
    year: number | null;
    minimum_incidents: number | null;
  };
  summary: string;
  assets: Array<{ asset_key: string; risk_score: number; matching_incidents: number }>;
  incidents: Array<{
    incident_id: string;
    asset_key: string;
    issue_family: string;
    confidence: number;
    supporting_work_orders: string[];
  }>;
  work_orders: Array<{
    work_order_id: string;
    date: string;
    description: string;
    issue_family: string;
    semantic_score: number;
  }>;
}

export interface TaxonomyPhrase {
  phrase: string;
  score: number;
}
