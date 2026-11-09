"use client";

import { formatDateTime, statusLabel } from "@/lib/format";
import type { AuditStep } from "@/types/api";

interface Props {
  auditId: string;
  steps: AuditStep[];
  onOpenStep: (step: number) => void;
}

export function StepGallery({ auditId, steps, onOpenStep }: Props) {
  return (
    <section aria-labelledby="steps-heading">
      <h2 id="steps-heading" className="text-lg font-semibold">
        What the agent saw
      </h2>
      {steps.length === 0 ? (
        <p className="mt-3 rounded-md border border-line bg-surface p-4 text-sm text-muted">
          No steps captured yet.
        </p>
      ) : (
        <ol className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {steps.map((step) => (
            <li key={step.step_number} className="overflow-hidden rounded-lg border border-line bg-surface">
              {step.has_evidence ? (
                <button
                  type="button"
                  className="block w-full bg-neutral-soft"
                  onClick={() => onOpenStep(step.step_number)}
                  aria-label={`Open the screenshot for step ${step.step_number}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/api/audits/${auditId}/steps/${step.step_number}/screenshot`}
                    alt={`Screenshot at step ${step.step_number}`}
                    loading="lazy"
                    className="h-40 w-full object-cover object-top"
                  />
                </button>
              ) : (
                <div className="flex h-40 items-center justify-center bg-neutral-soft text-sm text-muted">
                  No screenshot
                </div>
              )}
              <div className="space-y-1 p-3 text-sm">
                <p className="font-medium">
                  Step {step.step_number}
                  {step.page_title ? `: ${step.page_title}` : ""}
                </p>
                {step.action_description ? <p className="text-muted">{step.action_description}</p> : null}
                <p className="break-all text-xs text-muted">{step.page_url}</p>
                <p className="text-xs text-muted">
                  Capture: {statusLabel(step.status)} - Analysis: {statusLabel(step.analysis_status)}
                  {step.captured_at ? ` - ${formatDateTime(step.captured_at)}` : ""}
                </p>
                {step.dom_truncated ? (
                  <p className="text-xs text-warn">The page text was cut short before analysis.</p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
