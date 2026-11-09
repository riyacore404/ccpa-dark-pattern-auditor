// Shapes returned by the backend API. Mirrors backend/app/schemas/api.py.

export type AuditStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export const ACTIVE_STATUSES: readonly string[] = ["QUEUED", "RUNNING"];

export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.includes(status);
}

export type ReviewDecision = "CONFIRMED" | "REJECTED" | "INCONCLUSIVE";

export const REVIEW_DECISIONS: readonly ReviewDecision[] = ["CONFIRMED", "REJECTED", "INCONCLUSIVE"];

export interface AuditSummary {
  id: string;
  status: string;
  domain: string;
  requested_url: string;
  trigger_source: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  agent_provider: string | null;
  agent_run_id: string | null;
  vision_model: string | null;
  taxonomy_version: string;
  step_count: number;
  finding_count: number;
}

export interface AuditStep {
  step_number: number;
  status: string;
  analysis_status: string;
  action_description: string | null;
  page_title: string | null;
  page_url: string;
  page_url_source: string | null;
  captured_at: string | null;
  screenshot_sha256: string | null;
  dom_sha256: string | null;
  dom_truncated: boolean;
  has_evidence: boolean;
}

export interface EvidenceItem {
  kind: string;
  observation: string;
  verified: boolean;
}

export interface AuditFinding {
  id: string;
  step_number: number;
  category: string;
  confidence_score: number;
  grounding: string | null;
  explanation: string;
  observed_behavior: string;
  suggested_fix: string | null;
  offending_element_selector: string | null;
  legal_reference: string;
  review_status: string;
  evidence: EvidenceItem[];
  model_provider: string | null;
  model_version: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewer_reference: string | null;
  review_notes: string | null;
}

export interface AuditDetail {
  audit: AuditSummary;
  steps: AuditStep[];
  findings: AuditFinding[];
}

export interface ReviewInput {
  decision: ReviewDecision;
  reviewer: string;
  notes?: string;
}
