import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = { value: undefined as string | undefined };

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "ccpa_session" && cookieStore.value ? { name, value: cookieStore.value } : undefined,
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));

import { POST as postAudit } from "@/app/api/audits/route";
import { POST as postCancel } from "@/app/api/audits/[id]/cancel/route";
import { PATCH as patchFinding } from "@/app/api/audits/[id]/findings/[findingId]/route";
import { GET as getDetail } from "@/app/api/audits/[id]/route";
import { GET as getShot } from "@/app/api/audits/[id]/steps/[step]/screenshot/route";
import { POST as postLogin } from "@/app/api/login/route";
import { POST as postLogout } from "@/app/api/logout/route";
import { errorResponse } from "@/lib/apiRoute";
import { loginLimiter } from "@/lib/loginLimiter";
import { createSessionToken } from "@/lib/session";

import { AUDIT_ID, ENV, FINDING_ID, PASSWORD, SECRET, TOKEN, audit, finding, step } from "./helpers";

const ORIGIN = { origin: "http://localhost:3000", host: "localhost:3000" };
const ctx = <T,>(params: T) => ({ params: Promise.resolve(params) });

function req(method: string, url: string, body?: unknown, headers: Record<string, string> = ORIGIN) {
  return new Request(`http://localhost:3000${url}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  for (const [k, v] of Object.entries(ENV)) vi.stubEnv(k, v);
  cookieStore.value = createSessionToken(SECRET);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  loginLimiter.reset();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("every data route needs a session", () => {
  const calls: [string, () => Promise<Response>][] = [
    ["create audit", () => postAudit(req("POST", "/api/audits", { url: "https://a.example" }))],
    ["audit detail", () => getDetail(req("GET", "/api/audits/x", undefined, {}), ctx({ id: AUDIT_ID }))],
    ["cancel", () => postCancel(req("POST", "/api/audits/x/cancel"), ctx({ id: AUDIT_ID }))],
    [
      "review",
      () =>
        patchFinding(
          req("PATCH", "/api/audits/x/findings/y", { decision: "CONFIRMED", reviewer: "R" }),
          ctx({ id: AUDIT_ID, findingId: FINDING_ID }),
        ),
    ],
    ["screenshot", () => getShot(req("GET", "/api/x", undefined, {}), ctx({ id: AUDIT_ID, step: "1" }))],
  ];

  it.each(calls)("%s refuses a visitor with no session", async (_name, run) => {
    cookieStore.value = undefined;
    const response = await run();
    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(calls)("%s refuses a forged session", async (_name, run) => {
    cookieStore.value = createSessionToken("x".repeat(40));
    expect((await run()).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses everything when the dashboard is not configured", async () => {
    vi.stubEnv("SESSION_SECRET", "");
    expect((await calls[1]![1]()).status).toBe(401);
  });
});

describe("changes must come from the dashboard itself", () => {
  it.each([
    ["create", () => postAudit(req("POST", "/api/audits", { url: "https://a.example" }, { origin: "https://evil.example", host: "localhost:3000" }))],
    ["cancel", () => postCancel(req("POST", "/api/x", undefined, {}), ctx({ id: AUDIT_ID }))],
    [
      "review",
      () =>
        patchFinding(
          req("PATCH", "/api/x", { decision: "CONFIRMED", reviewer: "R" }, { origin: "https://evil.example", host: "localhost:3000" }),
          ctx({ id: AUDIT_ID, findingId: FINDING_ID }),
        ),
    ],
  ])("%s is refused cross-origin even with a valid session", async (_n, run) => {
    const response = await run();
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("login and logout", () => {
  it("signs in with the right password and sets a locked-down cookie", async () => {
    const response = await postLogin(req("POST", "/api/login", { password: PASSWORD }));
    expect(response.status).toBe(200);
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("ccpa_session=");
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).toContain("samesite=strict");
    expect(cookie).not.toContain(PASSWORD);
    expect(cookie).not.toContain(TOKEN);
  });

  it("refuses a wrong password without setting a cookie", async () => {
    const response = await postLogin(req("POST", "/api/login", { password: "nope nope nope" }));
    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("refuses cross-origin and malformed login attempts", async () => {
    const cross = await postLogin(req("POST", "/api/login", { password: PASSWORD }, { origin: "https://evil.example", host: "localhost:3000" }));
    expect(cross.status).toBe(403);
    expect((await postLogin(req("POST", "/api/login", { password: 5 }))).status).toBe(400);
    expect((await postLogin(req("POST", "/api/login", {}))).status).toBe(400);
    expect((await postLogin(req("POST", "/api/login", { password: "x".repeat(300) }))).status).toBe(400);
  });

  it("locks out after too many wrong passwords, even for the right one", async () => {
    for (let i = 0; i < 10; i++) await postLogin(req("POST", "/api/login", { password: "wrong password!" }));
    const blocked = await postLogin(req("POST", "/api/login", { password: PASSWORD }));
    expect(blocked.status).toBe(429);
  });

  it("says so, without detail, when the dashboard is not configured", async () => {
    vi.stubEnv("DASHBOARD_PASSWORD", "");
    const response = await postLogin(req("POST", "/api/login", { password: PASSWORD }));
    expect(response.status).toBe(500);
    expect(await response.text()).not.toContain(SECRET);
  });

  it("logout clears the cookie and is same-origin only", async () => {
    const ok = await postLogout(req("POST", "/api/logout"));
    expect(ok.headers.get("set-cookie")).toContain("Max-Age=0");
    expect((await postLogout(req("POST", "/api/logout", undefined, {}))).status).toBe(403);
  });
});

describe("proxying to the backend", () => {
  it("creates an audit and returns only the id and status", async () => {
    fetchMock.mockResolvedValue(json({ session_id: AUDIT_ID, status: "QUEUED" }, 202));
    const response = await postAudit(req("POST", "/api/audits", { url: " https://shop.example.com " }));
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ session_id: AUDIT_ID, status: "QUEUED" });
    const sent = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body));
    expect(sent.url).toBe("https://shop.example.com");
  });

  it("passes the backend's reason for refusing a target", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Target host is not allowed." }, 422));
    const response = await postAudit(req("POST", "/api/audits", { url: "http://localhost" }));
    expect(response.status).toBe(422);
    expect((await response.json()).error).toBe("Target host is not allowed.");
  });

  it("rejects a bad create body before calling the backend", async () => {
    for (const body of [{}, { url: 5 }, { url: "" }, undefined]) {
      expect((await postAudit(req("POST", "/api/audits", body))).status).toBe(422);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns an audit's detail", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      json(url.endsWith("/steps") ? [step(1)] : url.endsWith("/findings") ? [finding()] : audit()),
    );
    const response = await getDetail(req("GET", "/api/audits/x", undefined, {}), ctx({ id: AUDIT_ID }));
    const body = await response.json();
    expect(body.audit.id).toBe(AUDIT_ID);
    expect(body.steps).toHaveLength(1);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("validates a review and forwards it", async () => {
    fetchMock.mockResolvedValue(json(finding({ review_status: "CONFIRMED" })));
    const ok = await patchFinding(
      req("PATCH", "/x", { decision: "CONFIRMED", reviewer: " Riya ", notes: " ok " }),
      ctx({ id: AUDIT_ID, findingId: FINDING_ID }),
    );
    expect(ok.status).toBe(200);
    const sent = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body));
    expect(sent).toEqual({ decision: "CONFIRMED", reviewer: "Riya", notes: "ok" });

    fetchMock.mockClear();
    for (const bad of [{ decision: "PENDING_REVIEW", reviewer: "R" }, { decision: "CONFIRMED" }, { decision: "CONFIRMED", reviewer: "a\nb" }]) {
      const r = await patchFinding(req("PATCH", "/x", bad), ctx({ id: AUDIT_ID, findingId: FINDING_ID }));
      expect(r.status).toBe(422);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 404 for ids that are not UUIDs without calling the backend", async () => {
    const r = await getDetail(req("GET", "/x", undefined, {}), ctx({ id: "../../etc" }));
    expect(r.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("streams a screenshot with safe headers", async () => {
    fetchMock.mockResolvedValue(new Response(new Uint8Array([137, 80]), { headers: { "Content-Type": "image/png" } }));
    const r = await getShot(req("GET", "/x", undefined, {}), ctx({ id: AUDIT_ID, step: "2" }));
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("image/png");
    expect(r.headers.get("x-content-type-options")).toBe("nosniff");
    expect(r.headers.get("cache-control")).toBe("private, no-store");
    expect(r.headers.get("content-security-policy")).toContain("default-src 'none'");
  });

  it("answers 404 for bad step numbers", async () => {
    for (const bad of ["0", "abc", "9999", "1.5"]) {
      const r = await getShot(req("GET", "/x", undefined, {}), ctx({ id: AUDIT_ID, step: bad }));
      expect(r.status).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("backend failures never leak", () => {
  it.each([
    [401, 502, "credentials"],
    [403, 502, "credentials"],
    [500, 502, "could not complete"],
    [404, 404, "Audit not found."],
  ])("backend %i becomes %i", async (backendStatus, expected, text) => {
    fetchMock.mockImplementation(async () =>
      json({ detail: backendStatus === 404 ? "Audit not found." : `secret ${TOKEN}` }, backendStatus),
    );
    const r = await getDetail(req("GET", "/x", undefined, {}), ctx({ id: AUDIT_ID }));
    expect(r.status).toBe(expected);
    const body = await r.text();
    expect(body).toContain(text);
    expect(body).not.toContain(TOKEN);
  });

  it("an unreachable backend is a 503", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const r = await getDetail(req("GET", "/x", undefined, {}), ctx({ id: AUDIT_ID }));
    expect(r.status).toBe(503);
  });

  it("a fetch that throws for any reason is treated as unreachable", async () => {
    fetchMock.mockImplementation(async () => {
      throw new RangeError(`oops ${TOKEN}`);
    });
    const r = await postCancel(req("POST", "/x"), ctx({ id: AUDIT_ID }));
    expect(r.status).toBe(503);
    expect(await r.text()).not.toContain(TOKEN);
  });

  it("a truly unexpected error is a plain 500 and is logged by type only", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const r = errorResponse(new RangeError(`oops ${TOKEN}`));
    expect(r.status).toBe(500);
    expect(await r.text()).not.toContain(TOKEN);
    expect(JSON.stringify(spy.mock.calls)).not.toContain(TOKEN);
  });
});
