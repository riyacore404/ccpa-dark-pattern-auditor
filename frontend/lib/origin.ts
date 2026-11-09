/**
 * CSRF guard for requests that change something. Browsers always send an
 * Origin header on cross-site POST and PATCH requests, so a request whose
 * Origin is missing or names another host is refused.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
