import { hasSession } from "@/lib/auth";
import { BackendError } from "@/lib/backend";
import { ConfigError } from "@/lib/config";
import { isSameOrigin } from "@/lib/origin";

export function jsonResponse(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
}

export function problem(status: number, message: string): Response {
  return jsonResponse({ error: message }, status);
}

/** Refuse the request unless the caller is signed in (and, for changes, same-origin). */
export async function guard(request: Request, mutating: boolean): Promise<Response | null> {
  if (!(await hasSession())) return problem(401, "Not signed in.");
  if (mutating && !isSameOrigin(request)) return problem(403, "Cross-origin request refused.");
  return null;
}

/** Turn any failure into a response that never carries internals or secrets. */
export function errorResponse(error: unknown): Response {
  if (error instanceof ConfigError) return problem(500, "The dashboard is not configured.");
  if (error instanceof BackendError) {
    if (error.status === 401 || error.status === 403) {
      return problem(502, "The backend refused the dashboard's credentials.");
    }
    if (error.status >= 400 && error.status < 500) {
      return problem(error.status, error.detail ?? "The request was not accepted.");
    }
    if (error.status === 503) return problem(503, "The backend is not reachable right now.");
    return problem(502, "The backend could not complete the request.");
  }
  console.error("dashboard route failed:", error instanceof Error ? error.name : "unknown");
  return problem(500, "Something went wrong.");
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return undefined;
  }
}
