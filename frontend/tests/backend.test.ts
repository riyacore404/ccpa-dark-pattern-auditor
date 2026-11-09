import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BackendError,
  cancelAudit,
  createAudit,
  fetchScreenshot,
  getAuditDetail,
  listAudits,
  reviewFinding,
} from "@/lib/backend";

import { AUDIT_ID, ENV, FINDING_ID, TOKEN, audit, finding, step } from "./helpers";

function respond(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  for (const [key, value] of Object.entries(ENV)) vi.stubEnv(key, value);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("backend client", () => {
  it("sends the bearer token and never follows redirects or caches", async () => {
    fetchMock.mockResolvedValue(respond([audit()]));
    await listAudits(10);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/audits?limit=10");
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(init.redirect).toBe("manual");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("keeps the page size within the backend's limits", async () => {
    fetchMock.mockImplementation(async () => respond([]));
    await listAudits(5000);
    await listAudits(0);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("limit=100");
    expect(fetchMock.mock.calls[1]?.[0]).toContain("limit=1");
  });

  it("loads an audit's summary, steps and findings together", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith("/steps")) return respond([step(1)]);
      if (url.endsWith("/findings")) return respond([finding()]);
      return respond(audit());
    });
    const detail = await getAuditDetail(AUDIT_ID);
    expect(detail.audit.id).toBe(AUDIT_ID);
    expect(detail.steps).toHaveLength(1);
    expect(detail.findings).toHaveLength(1);
  });

  it("creates audits as a DASHBOARD-triggered request", async () => {
    fetchMock.mockResolvedValue(respond({ session_id: AUDIT_ID, status: "QUEUED" }, { status: 202 }));
    await createAudit("https://shop.example.com");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      url: "https://shop.example.com",
      trigger_source: "DASHBOARD",
    });
  });

  it("posts a cancel and patches a review to the right paths", async () => {
    fetchMock.mockResolvedValue(respond(audit()));
    await cancelAudit(AUDIT_ID);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`http://127.0.0.1:8000/api/v1/audits/${AUDIT_ID}/cancel`);

    fetchMock.mockResolvedValue(respond(finding()));
    await reviewFinding(AUDIT_ID, FINDING_ID, { decision: "CONFIRMED", reviewer: "Riya" });
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:8000/api/v1/audits/${AUDIT_ID}/findings/${FINDING_ID}`);
    expect(init.method).toBe("PATCH");
  });

  it("refuses ids that are not UUIDs before any request is made", async () => {
    for (const bad of ["../../etc/passwd", "1", "", `${AUDIT_ID}/../x`, `${AUDIT_ID}?x=1`]) {
      await expect(getAuditDetail(bad)).rejects.toMatchObject({ status: 404 });
      await expect(cancelAudit(bad)).rejects.toMatchObject({ status: 404 });
    }
    await expect(reviewFinding(AUDIT_ID, "nope", { decision: "REJECTED", reviewer: "R" })).rejects.toBeInstanceOf(
      BackendError,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports a plain-string detail from the backend and nothing else", async () => {
    fetchMock.mockResolvedValue(respond({ detail: "Target host is not allowed." }, { status: 422 }));
    await expect(createAudit("http://localhost")).rejects.toMatchObject({
      status: 422,
      detail: "Target host is not allowed.",
    });

    fetchMock.mockResolvedValue(respond({ detail: [{ msg: "structured" }] }, { status: 422 }));
    await expect(createAudit("x")).rejects.toMatchObject({ status: 422, detail: null });

    fetchMock.mockResolvedValue(new Response("<html>boom</html>", { status: 500 }));
    await expect(listAudits()).rejects.toMatchObject({ status: 500, detail: null });
  });

  it("treats a network failure or timeout as 503", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    await expect(listAudits()).rejects.toMatchObject({ status: 503 });
  });

  it("never includes the token in an error", async () => {
    fetchMock.mockResolvedValue(respond({ detail: "bad" }, { status: 401 }));
    try {
      await listAudits();
    } catch (error) {
      expect(JSON.stringify(error)).not.toContain(TOKEN);
      expect(String((error as Error).message)).not.toContain(TOKEN);
    }
  });
});

describe("fetchScreenshot", () => {
  it("returns the image stream and its type", async () => {
    fetchMock.mockResolvedValue(
      new Response(new Uint8Array([1, 2, 3]), { headers: { "Content-Type": "image/png" } }),
    );
    const image = await fetchScreenshot(AUDIT_ID, 2);
    expect(image.contentType).toBe("image/png");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `http://127.0.0.1:8000/api/v1/audits/${AUDIT_ID}/steps/2/screenshot`,
    );
  });

  it("refuses anything that is not a plain image", async () => {
    for (const type of ["text/html", "image/svg+xml", "application/json", ""]) {
      fetchMock.mockResolvedValue(new Response("x", { headers: { "Content-Type": type } }));
      await expect(fetchScreenshot(AUDIT_ID, 1)).rejects.toMatchObject({ status: 502 });
    }
  });

  it("refuses bad step numbers without calling the backend", async () => {
    for (const bad of [0, -1, 1001, 1.5]) {
      await expect(fetchScreenshot(AUDIT_ID, bad)).rejects.toMatchObject({ status: 404 });
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
