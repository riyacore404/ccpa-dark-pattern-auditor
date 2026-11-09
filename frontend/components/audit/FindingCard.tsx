"use client";

import { useState } from "react";

import { ReviewStatusBadge } from "@/components/ui/StatusBadge";
import { buttonClass } from "@/components/ui/styles";
import { categoryLabel } from "@/lib/categories";
import { formatConfidence, formatDateTime } from "@/lib/format";
import type { AuditFinding } from "@/types/api";

import { ReviewForm } from "./ReviewForm";

interface Props {
  auditId: string;
  finding: AuditFinding;
  canViewStep: boolean;
  onOpenStep: (step: number) => void;
  onSaved: (finding: AuditFinding) => void;
}

export function FindingCard({ auditId, finding, canViewStep, onOpenStep, onSaved }: Props) {
  const pending = finding.review_status === "PENDING_REVIEW";
  const [editing, setEditing] = useState(false);

  return (
    <article className="rounded-lg border border-line bg-surface p-4" aria-label={categoryLabel(finding.category)}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold">{categoryLabel(finding.category)}</h3>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted" title="The model's confidence, not a legal finding">
            Confidence {formatConfidence(finding.confidence_score)}
          </span>
          <ReviewStatusBadge status={finding.review_status} />
        </div>
      </header>

      <p className="mt-3 text-sm">{finding.explanation}</p>

      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="font-medium">What was observed</dt>
          <dd className="text-muted">{finding.observed_behavior}</dd>
        </div>
        {finding.evidence.length > 0 ? (
          <div>
            <dt className="font-medium">Evidence</dt>
            <dd>
              <ul className="mt-1 space-y-1.5">
                {finding.evidence.map((item, index) => (
                  <li key={index} className="rounded-md bg-neutral-soft p-2">
                    <span
                      className={`mr-2 text-xs font-medium ${item.verified ? "text-ok" : "text-warn"}`}
                    >
                      {item.kind === "DOM_TEXT" ? "Page text" : "Screenshot"} -{" "}
                      {item.verified ? "found on the page" : "not machine-verified"}
                    </span>
                    <q className="break-words">{item.observation}</q>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
        {finding.offending_element_selector ? (
          <div>
            <dt className="font-medium">Element</dt>
            <dd>
              <code className="break-all rounded bg-neutral-soft px-1.5 py-0.5 text-xs">
                {finding.offending_element_selector}
              </code>
            </dd>
          </div>
        ) : null}
        {finding.suggested_fix ? (
          <div>
            <dt className="font-medium">Suggested fix</dt>
            <dd className="text-muted">{finding.suggested_fix}</dd>
          </div>
        ) : null}
        <div>
          <dt className="font-medium">Guideline reference</dt>
          <dd className="text-muted">{finding.legal_reference}</dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>Step {finding.step_number}</span>
        {finding.model_version ? <span>Model {finding.model_version}</span> : null}
        {canViewStep ? (
          <button type="button" className="text-accent hover:underline" onClick={() => onOpenStep(finding.step_number)}>
            View screenshot
          </button>
        ) : null}
      </div>

      {!pending && !editing ? (
        <div className="mt-4 rounded-md border border-line p-3 text-sm">
          <p>
            <span className="font-medium">{finding.reviewer_reference ?? "A reviewer"}</span>{" "}
            <span className="text-muted">on {formatDateTime(finding.reviewed_at)}</span>
          </p>
          {finding.review_notes ? <p className="mt-1 whitespace-pre-wrap">{finding.review_notes}</p> : null}
          <button type="button" className={`${buttonClass("secondary")} mt-3`} onClick={() => setEditing(true)}>
            Change decision
          </button>
        </div>
      ) : (
        <ReviewForm
          auditId={auditId}
          finding={finding}
          onSaved={(updated) => {
            setEditing(false);
            onSaved(updated);
          }}
        />
      )}
    </article>
  );
}
