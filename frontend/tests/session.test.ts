import { describe, expect, it } from "vitest";

import { LoginLimiter } from "@/lib/loginLimiter";
import { isSameOrigin } from "@/lib/origin";
import {
  SESSION_MAX_AGE_SECONDS,
  createSessionToken,
  passwordMatches,
  verifySessionToken,
} from "@/lib/session";

import { SECRET } from "./helpers";

const NOW = 1_800_000_000_000;

describe("session tokens", () => {
  it("verifies a fresh token", () => {
    expect(verifySessionToken(createSessionToken(SECRET, NOW), SECRET, NOW + 1000)).toBe(true);
  });

  it("expires after the maximum age", () => {
    const token = createSessionToken(SECRET, NOW);
    const justBefore = NOW + SESSION_MAX_AGE_SECONDS * 1000 - 1;
    expect(verifySessionToken(token, SECRET, justBefore)).toBe(true);
    expect(verifySessionToken(token, SECRET, NOW + SESSION_MAX_AGE_SECONDS * 1000)).toBe(false);
  });

  it("rejects a token signed with another secret", () => {
    expect(verifySessionToken(createSessionToken("o".repeat(40), NOW), SECRET, NOW)).toBe(false);
  });

  it("rejects a token whose expiry was edited", () => {
    const [, nonce, sig] = createSessionToken(SECRET, NOW).split(".");
    const forged = `${NOW + 10 ** 12}.${nonce}.${sig}`;
    expect(verifySessionToken(forged, SECRET, NOW)).toBe(false);
  });

  it.each(["", "abc", "1.2.3", "..", "1800000000000.short.sig", "a".repeat(500)])(
    "rejects malformed value %j",
    (value) => {
      expect(verifySessionToken(value, SECRET, NOW)).toBe(false);
    },
  );

  it("gives each token a different nonce", () => {
    expect(createSessionToken(SECRET, NOW)).not.toBe(createSessionToken(SECRET, NOW));
  });
});

describe("passwordMatches", () => {
  it("matches only the exact password", () => {
    expect(passwordMatches("correct horse battery", "correct horse battery")).toBe(true);
    expect(passwordMatches("correct horse batterY", "correct horse battery")).toBe(false);
    expect(passwordMatches("", "correct horse battery")).toBe(false);
    expect(passwordMatches("correct horse battery!", "correct horse battery")).toBe(false);
  });
});

describe("LoginLimiter", () => {
  it("blocks after the maximum failures and recovers when they age out", () => {
    let now = 0;
    const limiter = new LoginLimiter(3, 1000, () => now);
    for (let i = 0; i < 3; i++) {
      expect(limiter.isBlocked()).toBe(false);
      limiter.recordFailure();
    }
    expect(limiter.isBlocked()).toBe(true);
    now = 1001;
    expect(limiter.isBlocked()).toBe(false);
  });

  it("reset clears the failures", () => {
    const limiter = new LoginLimiter(1, 1000, () => 0);
    limiter.recordFailure();
    expect(limiter.isBlocked()).toBe(true);
    limiter.reset();
    expect(limiter.isBlocked()).toBe(false);
  });
});

describe("isSameOrigin", () => {
  const make = (headers: Record<string, string>) =>
    new Request("http://localhost:3000/api/x", { method: "POST", headers });

  it("accepts the dashboard's own origin", () => {
    expect(isSameOrigin(make({ origin: "http://localhost:3000", host: "localhost:3000" }))).toBe(true);
  });

  it.each([
    ["another site", { origin: "https://evil.example", host: "localhost:3000" }],
    ["another port", { origin: "http://localhost:4000", host: "localhost:3000" }],
    ["no Origin header", { host: "localhost:3000" }],
    ["no Host header", { origin: "http://localhost:3000" }],
    ["an unparseable Origin", { origin: "null", host: "localhost:3000" }],
  ])("refuses %s", (_label, headers) => {
    expect(isSameOrigin(make(headers))).toBe(false);
  });
});
