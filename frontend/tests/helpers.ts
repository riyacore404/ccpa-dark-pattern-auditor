import type {
  AuditFinding,
  AuditStep,
  AuditSummary,
} from "@/types/api";

export const TOKEN = "t".repeat(32);
export const PASSWORD = "correct horse battery";
export const SECRET = "s".repeat(40);
export const AUDIT_ID = "11111111-1111-4111-8111-111111111111";
export const FINDING_ID = "22222222-2222-4222-8222-222222222222";

export const ENV = {
  CCPA_API_BASE_URL: "http://127.0.0.1:8000",
  API_ACCESS_TOKEN: TOKEN,
  DASHBOARD_PASSWORD: PASSWORD,
  SESSION_SECRET: SECRET,
};

export function audit(overrides: Partial<AuditSummary> = {}): AuditSummary {
  return {
    id: AUDIT_ID,
    status: "COMPLETED",
    domain: "shop.example.com",
    requested_url: "https://shop.example.com/",
    trigger_source: "DASHBOARD",
    created_at: "2026-11-07T10:00:00Z",
    started_at: "2026-11-07T10:00:05Z",
    completed_at: "2026-11-07T10:01:35Z",
    error_code: null,
    error_message: null,
    agent_provider: "tinyfish",
    agent_run_id: "run-1",
    vision_model: "gemini-3.6-flash",
    taxonomy_version: "CCPA-2023",
    step_count: 2,
    finding_count: 1,
    ...overrides,
  };
}

export function step(n: number, overrides: Partial<AuditStep> = {}): AuditStep {
  return {
    step_number: n,
    status: "CAPTURED",
    analysis_status: "COMPLETED",
    action_description: `Action ${n}`,
    page_title: `Page ${n}`,
    page_url: `https://shop.example.com/p${n}`,
    page_url_source: "agent",
    captured_at: "2026-11-07T10:00:30Z",
    screenshot_sha256: "a".repeat(64),
    dom_sha256: "b".repeat(64),
    dom_truncated: false,
    has_evidence: true,
    ...overrides,
  };
}

export function finding(overrides: Partial<AuditFinding> = {}): AuditFinding {
  return {
    id: FINDING_ID,
    step_number: 1,
    category: "INTERFACE_INTERFERENCE",
    confidence_score: 0.85,
    grounding: "DOM_VERIFIED",
    explanation: "The marketing checkbox is pre-ticked.",
    observed_behavior: "The box is checked on load.",
    suggested_fix: "Leave it unticked.",
    offending_element_selector: "input[type='checkbox']:checked",
    legal_reference: "Guidelines, Annexure 1, item 6",
    review_status: "PENDING_REVIEW",
    evidence: [
      { kind: "DOM_TEXT", observation: "Receive emails about promotions", verified: true },
      { kind: "VISUAL", observation: "The box looks ticked", verified: false },
    ],
    model_provider: "gemini",
    model_version: "gemini-3.6-flash",
    created_at: "2026-11-07T10:01:00Z",
    reviewed_at: null,
    reviewer_reference: null,
    review_notes: null,
    ...overrides,
  };
}
