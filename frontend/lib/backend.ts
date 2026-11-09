// The only module that talks to the backend API, and the only one that holds
// its access token. Import it from server code (pages, route handlers) only.

import { loadConfig } from "@/lib/config";
import { isUuid, parseStepNumber } from "@/lib/ids";
import type {
  AuditDetail,
  AuditFinding,
  AuditStep,
  AuditSummary,
  ReviewInput,
} from "@/types/api";

const REQUEST_TIMEOUT_MS = 15_000;
const SCREENSHOT_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

export class BackendError extends Error {
  readonly status: number;
  /** A short message from the backend, only when it sent a plain string. */
  readonly detail: string | null;

  constructor(status: number, detail: string | null = null) {
    super(`Backend request failed with status ${status}`);
    this.name = "BackendError";
    this.status = status;
    this.detail = detail;
  }
}

interface CallOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
}

async function call(path: string, options: CallOptions = {}): Promise<Response> {
  const config = loadConfig();
  const headers: Record<string, string> = { Authorization: `Bearer ${config.apiToken}` };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(config.apiBase + path, {
      method: options.method ?? "GET",
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new BackendError(503);
  }

  if (!response.ok) {
    let detail: string | null = null;
    try {
      const data: unknown = await response.json();
      if (typeof data === "object" && data !== null && "detail" in data) {
        const value = (data as { detail: unknown }).detail;
        if (typeof value === "string" && value.length <= 300) detail = value;
      }
    } catch {
      // Not JSON: keep the generic error.
    }
    throw new BackendError(response.status, detail);
  }
  return response;
}

async function getJson<T>(path: string, options?: CallOptions): Promise<T> {
  const response = await call(path, options);
  return (await response.json()) as T;
}

function auditPath(id: string): string {
  if (!isUuid(id)) throw new BackendError(404);
  return `/api/v1/audits/${id}`;
}

export async function listAudits(limit = 50): Promise<AuditSummary[]> {
  const bounded = Math.min(Math.max(Math.trunc(limit), 1), 100);
  return getJson<AuditSummary[]>(`/api/v1/audits?limit=${bounded}`);
}

export async function getAuditDetail(id: string): Promise<AuditDetail> {
  const base = auditPath(id);
  const [audit, steps, findings] = await Promise.all([
    getJson<AuditSummary>(base),
    getJson<AuditStep[]>(`${base}/steps`),
    getJson<AuditFinding[]>(`${base}/findings`),
  ]);
  return { audit, steps, findings };
}

export async function createAudit(url: string): Promise<{ session_id: string; status: string }> {
  return getJson("/api/v1/audits", {
    method: "POST",
    body: { url, trigger_source: "DASHBOARD" },
  });
}

export async function cancelAudit(id: string): Promise<AuditSummary> {
  return getJson<AuditSummary>(`${auditPath(id)}/cancel`, { method: "POST" });
}

export async function reviewFinding(
  id: string,
  findingId: string,
  review: ReviewInput,
): Promise<AuditFinding> {
  if (!isUuid(findingId)) throw new BackendError(404);
  return getJson<AuditFinding>(`${auditPath(id)}/findings/${findingId}`, {
    method: "PATCH",
    body: review,
  });
}

/** The upstream screenshot response, checked to be a plain image. */
export async function fetchScreenshot(
  id: string,
  step: number,
): Promise<{ body: ReadableStream<Uint8Array>; contentType: string }> {
  if (parseStepNumber(String(step)) === null) throw new BackendError(404);
  const response = await call(`${auditPath(id)}/steps/${step}/screenshot`);
  const contentType = (response.headers.get("content-type") ?? "").split(";")[0]?.trim() ?? "";
  if (!SCREENSHOT_TYPES.has(contentType) || response.body === null) throw new BackendError(502);
  return { body: response.body, contentType };
}
