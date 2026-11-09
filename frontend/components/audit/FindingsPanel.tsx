"use client";

import { useState } from "react";

import { buttonClass } from "@/components/ui/styles";
import type { AuditFinding } from "@/types/api";

import { FindingCard } from "./FindingCard";

type Filter = "ALL" | "PENDING_REVIEW" | "CONFIRMED" | "REJECTED" | "INCONCLUSIVE";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "PENDING_REVIEW", label: "Pending" },
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "REJECTED", label: "Rejected" },
  { value: "INCONCLUSIVE", label: "Inconclusive" },
];

interface Props {
  auditId: string;
  findings: AuditFinding[];
  stepsWithEvidence: ReadonlySet<number>;
  onOpenStep: (step: number) => void;
  onSaved: (finding: AuditFinding) => void;
  stillRunning: boolean;
}

export function FindingsPanel({ auditId, findings, stepsWithEvidence, onOpenStep, onSaved, stillRunning }: Props) {
  const [filter, setFilter] = useState<Filter>("ALL");
  const count = (value: Filter) =>
    value === "ALL" ? findings.length : findings.filter((f) => f.review_status === value).length;
  const shown = filter === "ALL" ? findings : findings.filter((f) => f.review_status === filter);

  return (
    <section aria-labelledby="findings-heading">
      <h2 id="findings-heading" className="text-lg font-semibold">
        Findings
      </h2>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter findings by review status">
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            className={buttonClass(filter === value ? "primary" : "secondary")}
            onClick={() => setFilter(value)}
          >
            {label} ({count(value)})
          </button>
        ))}
      </div>
      <div className="mt-4 space-y-4">
        {shown.length === 0 ? (
          <p className="rounded-md border border-line bg-surface p-4 text-sm text-muted">
            {findings.length === 0
              ? stillRunning
                ? "No findings yet. The audit is still running."
                : "No findings were recorded for this audit."
              : "No findings match this filter."}
          </p>
        ) : (
          shown.map((finding) => (
            <FindingCard
              key={finding.id}
              auditId={auditId}
              finding={finding}
              canViewStep={stepsWithEvidence.has(finding.step_number)}
              onOpenStep={onOpenStep}
              onSaved={onSaved}
            />
          ))
        )}
      </div>
    </section>
  );
}
