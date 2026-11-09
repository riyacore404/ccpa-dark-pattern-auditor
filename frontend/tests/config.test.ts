import { describe, expect, it } from "vitest";

import { ConfigError, checkConfig, loadConfig } from "@/lib/config";

import { ENV, PASSWORD, TOKEN } from "./helpers";

describe("checkConfig", () => {
  it("accepts a complete environment", () => {
    const result = checkConfig(ENV);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.config.apiBase).toBe("http://127.0.0.1:8000");
  });

  it("defaults the API address to the local backend", () => {
    const { CCPA_API_BASE_URL: _unused, ...rest } = ENV;
    const result = checkConfig(rest);
    expect(result.ok && result.config.apiBase).toBe("http://127.0.0.1:8000");
  });

  it("strips a trailing slash from the API address", () => {
    const result = checkConfig({ ...ENV, CCPA_API_BASE_URL: "https://api.example.com/" });
    expect(result.ok && result.config.apiBase).toBe("https://api.example.com");
  });

  it.each([
    ["a missing token", { API_ACCESS_TOKEN: "" }, "API_ACCESS_TOKEN"],
    ["a short token", { API_ACCESS_TOKEN: "short" }, "API_ACCESS_TOKEN"],
    ["a missing password", { DASHBOARD_PASSWORD: undefined }, "DASHBOARD_PASSWORD"],
    ["a short password", { DASHBOARD_PASSWORD: "tiny" }, "DASHBOARD_PASSWORD"],
    ["a short session secret", { SESSION_SECRET: "x".repeat(31) }, "SESSION_SECRET"],
    ["a non-http API address", { CCPA_API_BASE_URL: "file:///etc/passwd" }, "CCPA_API_BASE_URL"],
    ["credentials in the API address", { CCPA_API_BASE_URL: "http://u:p@host" }, "CCPA_API_BASE_URL"],
    ["a query in the API address", { CCPA_API_BASE_URL: "http://host/?x=1" }, "CCPA_API_BASE_URL"],
    ["a garbage API address", { CCPA_API_BASE_URL: "not a url" }, "CCPA_API_BASE_URL"],
  ])("refuses %s", (_label, change, name) => {
    const result = checkConfig({ ...ENV, ...change });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problems.join(" ")).toContain(name);
  });

  it("never puts a secret value in the problem text", () => {
    const result = checkConfig({ ...ENV, SESSION_SECRET: "short-secret-value", DASHBOARD_PASSWORD: "tiny" });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      const text = result.problems.join(" ");
      expect(text).not.toContain("short-secret-value");
      expect(text).not.toContain(TOKEN);
      expect(text).not.toContain(PASSWORD);
    }
  });

  it("loadConfig throws a ConfigError that lists what is missing", () => {
    expect(() => loadConfig({})).toThrow(ConfigError);
    try {
      loadConfig({});
    } catch (error) {
      expect((error as ConfigError).problems.length).toBeGreaterThanOrEqual(3);
    }
  });
});
