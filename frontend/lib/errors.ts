import { BackendError } from "@/lib/backend";
import { ConfigError } from "@/lib/config";

/** A message safe to show on a page. */
export function describeError(error: unknown): string {
  if (error instanceof ConfigError) return "The dashboard is not configured.";
  if (error instanceof BackendError) {
    if (error.status === 401 || error.status === 403) {
      return "The backend refused the dashboard's credentials. Check API_ACCESS_TOKEN.";
    }
    if (error.status === 503) {
      return "The backend is not reachable. Is the API running?";
    }
    return "The backend could not complete the request.";
  }
  return "Something went wrong.";
}
