"use client";

import { useEffect, useState, type FormEvent } from "react";

import { INPUT_CLASS, buttonClass } from "@/components/ui/styles";
import { parseReviewInput } from "@/lib/validate";
import { REVIEW_DECISIONS, type AuditFinding, type ReviewDecision } from "@/types/api";

const REVIEWER_KEY = "ccpa_reviewer";

const DECISION_LABELS: Record<ReviewDecision, string> = {
  CONFIRMED: "Confirm: this is a dark pattern",
  REJECTED: "Reject: this is not a dark pattern",
  INCONCLUSIVE: "Inconclusive: cannot tell from this evidence",
};

interface Props {
  auditId: string;
  finding: AuditFinding;
  onSaved: (finding: AuditFinding) => void;
}

export function ReviewForm({ auditId, finding, onSaved }: Props) {
  const reviewed = REVIEW_DECISIONS.includes(finding.review_status as ReviewDecision);
  const [reviewer, setReviewer] = useState(finding.reviewer_reference ?? "");
  const [decision, setDecision] = useState<ReviewDecision | "">(
    reviewed ? (finding.review_status as ReviewDecision) : "",
  );
  const [notes, setNotes] = useState(finding.review_notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (reviewer) return;
    try {
      const saved = window.localStorage.getItem(REVIEWER_KEY);
      if (saved) setReviewer(saved);
    } catch {
      // Storage can be unavailable; the name just has to be typed.
    }
    // Only on first render: later edits must not be overwritten.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const parsed = parseReviewInput({ decision, reviewer, notes });
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/audits/${auditId}/findings/${finding.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.value),
      });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        setError(
          typeof data === "object" && data !== null && "error" in data
            ? String((data as { error: unknown }).error)
            : "Could not save the review.",
        );
        return;
      }
      try {
        window.localStorage.setItem(REVIEWER_KEY, parsed.value.reviewer);
      } catch {
        // Not saving the name is fine.
      }
      onSaved(data as AuditFinding);
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-3 border-t border-line pt-4">
      <fieldset>
        <legend className="text-sm font-medium">Your decision</legend>
        <div className="mt-2 space-y-1.5">
          {REVIEW_DECISIONS.map((value) => (
            <label key={value} className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name={`decision-${finding.id}`}
                value={value}
                checked={decision === value}
                onChange={() => setDecision(value)}
                className="mt-1"
              />
              <span>{DECISION_LABELS[value]}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor={`reviewer-${finding.id}`} className="block text-sm font-medium">
          Your name
        </label>
        <input
          id={`reviewer-${finding.id}`}
          type="text"
          maxLength={80}
          className={`${INPUT_CLASS} mt-1 sm:max-w-xs`}
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
        />
      </div>
      <div>
        <label htmlFor={`notes-${finding.id}`} className="block text-sm font-medium">
          Notes (optional)
        </label>
        <textarea
          id={`notes-${finding.id}`}
          rows={3}
          maxLength={2000}
          className={`${INPUT_CLASS} mt-1`}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
      </div>
      <p role="alert" className="min-h-5 text-sm text-bad">
        {error}
      </p>
      <button type="submit" className={buttonClass("primary")} disabled={busy}>
        {busy ? "Saving..." : reviewed ? "Update review" : "Save review"}
      </button>
    </form>
  );
}
