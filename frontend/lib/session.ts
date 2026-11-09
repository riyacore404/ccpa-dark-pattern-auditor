import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "ccpa_session";
export const SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;

const TOKEN_PATTERN = /^[0-9]{1,16}\.[A-Za-z0-9_-]{16,64}\.[A-Za-z0-9_-]{43}$/;

function sign(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

/** A signed, expiring session value: "<expiry-ms>.<nonce>.<signature>". */
export function createSessionToken(secret: string, nowMs: number = Date.now()): string {
  const expires = nowMs + SESSION_MAX_AGE_SECONDS * 1000;
  const payload = `${expires}.${randomBytes(16).toString("base64url")}`;
  return `${payload}.${sign(secret, payload)}`;
}

export function verifySessionToken(
  token: string,
  secret: string,
  nowMs: number = Date.now(),
): boolean {
  if (!TOKEN_PATTERN.test(token)) return false;
  const lastDot = token.lastIndexOf(".");
  const payload = token.slice(0, lastDot);
  const given = Buffer.from(token.slice(lastDot + 1));
  const expected = Buffer.from(sign(secret, payload));
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return false;
  const expires = Number(payload.slice(0, payload.indexOf(".")));
  return Number.isFinite(expires) && expires > nowMs;
}

/** Constant-time password comparison that does not leak the length. */
export function passwordMatches(input: string, expected: string): boolean {
  const a = createHash("sha256").update(input).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}
