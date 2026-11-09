export function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date) + " UTC";
}

export function formatConfidence(score: number): string {
  if (!Number.isFinite(score)) return "-";
  return `${Math.round(Math.min(Math.max(score, 0), 1) * 100)}%`;
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "-";
  const seconds = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "-";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function statusLabel(status: string): string {
  const words = status.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const PARTIAL_RESULTS_NOTE =
  "Some steps were not fully analysed. The findings below come from the steps that were.";

const ERROR_NOTES: Record<string, string> = {
  PARTIAL_RESULTS: PARTIAL_RESULTS_NOTE,
  STEP_LIMIT_EXCEEDED:
    "The browsing agent reached the step limit before finishing. Findings from the steps it completed are kept.",
  CANCELLED_BY_USER: "This audit was cancelled.",
  NO_EVIDENCE_CAPTURED: "No usable evidence was captured, so nothing could be analysed.",
};

export function errorNote(code: string | null, message: string | null): string | null {
  if (!code) return null;
  return ERROR_NOTES[code] ?? message ?? "The audit did not finish normally.";
}
