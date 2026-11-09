"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { INPUT_CLASS, buttonClass } from "@/components/ui/styles";
import { parseAuditUrl } from "@/lib/validate";

export function NewAuditForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const parsed = parseAuditUrl(url);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/audits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: parsed.value }),
      });
      const data: unknown = await response.json().catch(() => null);
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) {
        setError(
          typeof data === "object" && data !== null && "error" in data
            ? String((data as { error: unknown }).error)
            : "Could not start the audit.",
        );
        return;
      }
      const id =
        typeof data === "object" && data !== null && "session_id" in data
          ? String((data as { session_id: unknown }).session_id)
          : null;
      if (id) router.push(`/audits/${id}`);
      else router.refresh();
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 rounded-lg border border-line bg-surface p-4">
      <label htmlFor="audit-url" className="block text-sm font-medium">
        Website address
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <input
          id="audit-url"
          type="text"
          inputMode="url"
          autoComplete="off"
          placeholder="https://shop.example.com"
          className={INPUT_CLASS}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <button type="submit" className={`${buttonClass("primary")} shrink-0`} disabled={busy}>
          {busy ? "Starting..." : "Start audit"}
        </button>
      </div>
      <p role="alert" className="mt-2 min-h-5 text-sm text-bad">
        {error}
      </p>
      <p className="text-xs text-muted">
        Each audit uses a live browsing agent and model calls. Only audit sites you are allowed to test.
      </p>
    </form>
  );
}
