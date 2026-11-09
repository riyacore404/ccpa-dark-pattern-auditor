// Server-side settings. Read only from server code: nothing here is ever
// exposed to the browser, and the backend token must stay that way.

export interface DashboardConfig {
  apiBase: string;
  apiToken: string;
  dashboardPassword: string;
  sessionSecret: string;
}

export type ConfigCheck =
  | { ok: true; config: DashboardConfig }
  | { ok: false; problems: string[] };

export class ConfigError extends Error {
  readonly problems: string[];

  constructor(problems: string[]) {
    super(`Dashboard is not configured: ${problems.join("; ")}`);
    this.name = "ConfigError";
    this.problems = problems;
  }
}

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

function parseApiBase(raw: string | undefined): string | null {
  const value = (raw ?? "").trim() || DEFAULT_API_BASE;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  if (url.username || url.password || url.search || url.hash) return null;
  return url.origin + url.pathname.replace(/\/+$/, "");
}

/** Check the environment. Problems name the variable and the rule, never a value. */
export function checkConfig(env: Record<string, string | undefined> = process.env): ConfigCheck {
  const problems: string[] = [];

  const apiBase = parseApiBase(env.CCPA_API_BASE_URL);
  if (apiBase === null) {
    problems.push("CCPA_API_BASE_URL must be an http(s) URL without credentials or a query");
  }

  const apiToken = (env.API_ACCESS_TOKEN ?? "").trim();
  if (apiToken.length < 24) problems.push("API_ACCESS_TOKEN must be set (at least 24 characters)");

  const dashboardPassword = env.DASHBOARD_PASSWORD ?? "";
  if (dashboardPassword.length < 12) {
    problems.push("DASHBOARD_PASSWORD must be set (at least 12 characters)");
  }

  const sessionSecret = env.SESSION_SECRET ?? "";
  if (sessionSecret.length < 32) problems.push("SESSION_SECRET must be set (at least 32 characters)");

  if (problems.length > 0 || apiBase === null) return { ok: false, problems };
  return { ok: true, config: { apiBase, apiToken, dashboardPassword, sessionSecret } };
}

export function loadConfig(env: Record<string, string | undefined> = process.env): DashboardConfig {
  const result = checkConfig(env);
  if (!result.ok) throw new ConfigError(result.problems);
  return result.config;
}
