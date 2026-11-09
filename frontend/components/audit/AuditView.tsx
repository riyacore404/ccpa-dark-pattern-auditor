"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuditStatusBadge } from "@/components/ui/StatusBadge";
import { errorNote, formatDateTime, formatDuration } from "@/lib/format";
import { isActiveStatus, type AuditDetail, type AuditFinding } from "@/types/api";

import { CancelButton } from "./CancelButton";
import { FindingsPanel } from "./FindingsPanel";
import { ScreenshotModal } from "./ScreenshotModal";
import { StepGallery } from "./StepGallery";

const POLL_MS = 3000;

export function AuditView({ initial }: { initial: AuditDetail }) {
  const [detail, setDetail] = useState<AuditDetail>(initial);
  const [openStep, setOpenStep] = useState<number | null>(null);
  const [pollError, setPollError] = useState(false);
  const inFlight = useRef(false);

  const auditId = detail.audit.id;
  const active = isActiveStatus(detail.audit.status);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const response = await fetch(`/api/audits/${auditId}`, { cache: "no-store" });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) {
        setPollError(true);
        return;
      }
      const fresh = (await response.json()) as AuditDetail;
      setPollError(false);
      // Keep reviews made here that the poll could have raced past.
      setDetail((current) => ({
        ...fresh,
        findings: fresh.findings.map((finding) => {
          const local = current.findings.find((f) => f.id === finding.id);
          return local && local.reviewed_at && !finding.reviewed_at ? local : finding;
        }),
      }));
    } catch {
      setPollError(true);
    } finally {
      inFlight.current = false;
    }
  }, [auditId]);

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [active, refresh]);

  const onSaved = useCallback((updated: AuditFinding) => {
    setDetail((current) => ({
      ...current,
      findings: current.findings.map((f) => (f.id === updated.id ? updated : f)),
    }));
  }, []);

  const stepsWithEvidence = useMemo(
    () => new Set(detail.steps.filter((s) => s.has_evidence).map((s) => s.step_number)),
    [detail.steps],
  );

  const { audit } = detail;
  const note = errorNote(audit.error_code, audit.error_message);

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-accent hover:underline">
          Back to audits
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{audit.domain}</h1>
            <p className="break-all text-sm text-muted">{audit.requested_url}</p>
          </div>
          <div className="flex items-center gap-3">
            <AuditStatusBadge status={audit.status} />
            {active ? <CancelButton auditId={audit.id} onDone={() => void refresh()} /> : null}
          </div>
        </div>
        <dl className="mt-4 grid gap-3 rounded-lg border border-line bg-surface p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-muted">Started</dt>
            <dd>{formatDateTime(audit.started_at ?? audit.created_at)}</dd>
          </div>
          <div>
            <dt className="text-muted">Duration</dt>
            <dd>{formatDuration(audit.started_at, audit.completed_at)}</dd>
          </div>
          <div>
            <dt className="text-muted">Steps captured</dt>
            <dd>{audit.step_count}</dd>
          </div>
          <div>
            <dt className="text-muted">Findings</dt>
            <dd>{detail.findings.length}</dd>
          </div>
        </dl>
        {active ? (
          <p className="mt-3 text-sm text-muted" aria-live="polite">
            The audit is {audit.status === "QUEUED" ? "waiting to start" : "running"}. This page updates
            automatically.
            {pollError ? " (Could not refresh just now; retrying.)" : ""}
          </p>
        ) : null}
        {note ? (
          <p className="mt-3 rounded-md border border-line bg-neutral-soft p-3 text-sm">{note}</p>
        ) : null}
        <p className="mt-3 rounded-md border border-warn bg-warn-soft p-3 text-sm text-warn">
          Findings are machine-generated hypotheses for human review, not legal verdicts. Check each one
          against the screenshot and the page before deciding.
        </p>
      </div>

      <FindingsPanel
        auditId={audit.id}
        findings={detail.findings}
        stepsWithEvidence={stepsWithEvidence}
        onOpenStep={setOpenStep}
        onSaved={onSaved}
        stillRunning={active}
      />
      <StepGallery auditId={audit.id} steps={detail.steps} onOpenStep={setOpenStep} />

      {openStep !== null ? (
        <ScreenshotModal auditId={audit.id} step={openStep} onClose={() => setOpenStep(null)} />
      ) : null}
    </div>
  );
}
