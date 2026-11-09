import { statusLabel } from "@/lib/format";

import { Badge, type Tone } from "./Badge";

const AUDIT_TONES: Record<string, Tone> = {
  QUEUED: "neutral",
  RUNNING: "info",
  COMPLETED: "ok",
  FAILED: "bad",
  CANCELLED: "neutral",
};

const REVIEW_TONES: Record<string, Tone> = {
  PENDING_REVIEW: "warn",
  CONFIRMED: "bad",
  REJECTED: "neutral",
  INCONCLUSIVE: "info",
};

const REVIEW_LABELS: Record<string, string> = {
  PENDING_REVIEW: "Pending review",
  CONFIRMED: "Confirmed",
  REJECTED: "Rejected",
  INCONCLUSIVE: "Inconclusive",
};

export function AuditStatusBadge({ status }: { status: string }) {
  return <Badge tone={AUDIT_TONES[status] ?? "neutral"}>{statusLabel(status)}</Badge>;
}

export function ReviewStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={REVIEW_TONES[status] ?? "neutral"}>{REVIEW_LABELS[status] ?? statusLabel(status)}</Badge>
  );
}
