"use client";

import { useState } from "react";

import { buttonClass } from "@/components/ui/styles";

export function CancelButton({ auditId, onDone }: { auditId: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    if (busy || !window.confirm("Cancel this audit? Evidence captured so far is kept.")) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/audits/${auditId}/cancel`, { method: "POST" });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => null);
        setError(
          typeof data === "object" && data !== null && "error" in data
            ? String((data as { error: unknown }).error)
            : "Could not cancel the audit.",
        );
        return;
      }
      onDone();
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button type="button" className={buttonClass("danger")} onClick={cancel} disabled={busy}>
        {busy ? "Cancelling..." : "Cancel audit"}
      </button>
      {error ? (
        <p role="alert" className="mt-1 text-sm text-bad">
          {error}
        </p>
      ) : null}
    </div>
  );
}
