import { REVIEW_DECISIONS, type ReviewDecision, type ReviewInput } from "@/types/api";

export const MAX_REVIEWER_LENGTH = 80;
export const MAX_NOTES_LENGTH = 2000;
export const MAX_URL_LENGTH = 2048;

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

function hasControlCharacters(text: string): boolean {
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code < 32 || code === 127) return true;
  }
  return false;
}

/** Same rules as the backend, so a reviewer sees problems before sending. */
export function parseReviewInput(raw: unknown): Parsed<ReviewInput> {
  if (typeof raw !== "object" || raw === null) return { ok: false, error: "Invalid request." };
  const body = raw as Record<string, unknown>;

  const decision = body.decision;
  if (typeof decision !== "string" || !REVIEW_DECISIONS.includes(decision as ReviewDecision)) {
    return { ok: false, error: "Choose Confirm, Reject or Inconclusive." };
  }

  const reviewer = typeof body.reviewer === "string" ? body.reviewer.trim() : "";
  if (!reviewer) return { ok: false, error: "Enter your name." };
  if (reviewer.length > MAX_REVIEWER_LENGTH || hasControlCharacters(reviewer)) {
    return { ok: false, error: `Name must be plain text, up to ${MAX_REVIEWER_LENGTH} characters.` };
  }

  let notes: string | undefined;
  if (body.notes !== undefined && body.notes !== null) {
    if (typeof body.notes !== "string") return { ok: false, error: "Invalid notes." };
    const trimmed = body.notes.trim();
    if (trimmed.length > MAX_NOTES_LENGTH) {
      return { ok: false, error: `Notes can be at most ${MAX_NOTES_LENGTH} characters.` };
    }
    notes = trimmed || undefined;
  }

  return { ok: true, value: { decision: decision as ReviewDecision, reviewer, notes } };
}

export function parseAuditUrl(raw: unknown): Parsed<string> {
  if (typeof raw !== "string") return { ok: false, error: "Enter a website address." };
  const url = raw.trim();
  if (!url) return { ok: false, error: "Enter a website address." };
  if (url.length > MAX_URL_LENGTH) return { ok: false, error: "That address is too long." };
  return { ok: true, value: url };
}
