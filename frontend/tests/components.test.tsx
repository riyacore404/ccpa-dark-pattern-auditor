// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

import { AuditView } from "@/components/audit/AuditView";
import { FindingCard } from "@/components/audit/FindingCard";
import { NewAuditForm } from "@/components/audit/NewAuditForm";
import { ReviewForm } from "@/components/audit/ReviewForm";
import { StepGallery } from "@/components/audit/StepGallery";

import { AUDIT_ID, FINDING_ID, audit, finding, step } from "./helpers";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
  push.mockClear();
  refresh.mockClear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function choose(label: RegExp) {
  fireEvent.click(screen.getByLabelText(label));
}

describe("ReviewForm", () => {
  it("asks for a decision and a name before sending anything", () => {
    const onSaved = vi.fn();
    render(<ReviewForm auditId={AUDIT_ID} finding={finding()} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));
    expect(screen.getByRole("alert").textContent).toContain("Choose Confirm");

    choose(/Confirm:/);
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));
    expect(screen.getByRole("alert").textContent).toContain("Enter your name");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("sends the review and hands back the updated finding", async () => {
    const updated = finding({ review_status: "CONFIRMED", reviewer_reference: "Riya" });
    fetchMock.mockResolvedValue(json(updated));
    const onSaved = vi.fn();
    render(<ReviewForm auditId={AUDIT_ID} finding={finding()} onSaved={onSaved} />);

    choose(/Confirm:/);
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: " Riya " } });
    fireEvent.change(screen.getByLabelText(/Notes/), { target: { value: "Checked in a browser" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/audits/${AUDIT_ID}/findings/${FINDING_ID}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({
      decision: "CONFIRMED",
      reviewer: "Riya",
      notes: "Checked in a browser",
    });
    expect(window.localStorage.getItem("ccpa_reviewer")).toBe("Riya");
  });

  it("remembers the reviewer's name between findings", () => {
    window.localStorage.setItem("ccpa_reviewer", "Riya");
    render(<ReviewForm auditId={AUDIT_ID} finding={finding()} onSaved={vi.fn()} />);
    expect((screen.getByLabelText("Your name") as HTMLInputElement).value).toBe("Riya");
  });

  it("shows the server's reason when saving fails and does not report success", async () => {
    fetchMock.mockResolvedValue(json({ error: "Finding not found in this audit." }, 404));
    const onSaved = vi.fn();
    render(<ReviewForm auditId={AUDIT_ID} finding={finding()} onSaved={onSaved} />);
    choose(/Reject:/);
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Riya" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("not found"));
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("starts from the existing decision when changing a review", () => {
    render(
      <ReviewForm
        auditId={AUDIT_ID}
        finding={finding({ review_status: "REJECTED", reviewer_reference: "Sam", review_notes: "n" })}
        onSaved={vi.fn()}
      />,
    );
    expect((screen.getByLabelText(/Reject:/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Your name") as HTMLInputElement).value).toBe("Sam");
    expect(screen.getByRole("button", { name: "Update review" })).toBeTruthy();
  });
});

describe("FindingCard", () => {
  const base = { auditId: AUDIT_ID, canViewStep: true, onOpenStep: vi.fn(), onSaved: vi.fn() };

  it("shows the category, confidence and what was and was not verified", () => {
    render(<FindingCard {...base} finding={finding()} />);
    expect(screen.getByRole("heading", { name: "Interface interference" })).toBeTruthy();
    expect(screen.getByText(/Confidence 85%/)).toBeTruthy();
    expect(screen.getByText("Pending review")).toBeTruthy();
    expect(screen.getByText(/Page text - found on the page/)).toBeTruthy();
    expect(screen.getByText(/Screenshot - not machine-verified/)).toBeTruthy();
    expect(screen.getByText("Receive emails about promotions")).toBeTruthy();
  });

  it("opens the screenshot for its step, only when one exists", () => {
    const onOpenStep = vi.fn();
    const { rerender } = render(<FindingCard {...base} onOpenStep={onOpenStep} finding={finding({ step_number: 3 })} />);
    fireEvent.click(screen.getByRole("button", { name: "View screenshot" }));
    expect(onOpenStep).toHaveBeenCalledWith(3);
    rerender(<FindingCard {...base} canViewStep={false} finding={finding()} />);
    expect(screen.queryByRole("button", { name: "View screenshot" })).toBeNull();
  });

  it("shows who decided and when once reviewed, and reopens the form on request", () => {
    render(
      <FindingCard
        {...base}
        finding={finding({
          review_status: "CONFIRMED",
          reviewer_reference: "Riya",
          reviewed_at: "2026-11-07T11:00:00Z",
          review_notes: "Looks right",
        })}
      />,
    );
    expect(screen.getByText("Confirmed")).toBeTruthy();
    expect(screen.getByText("Riya")).toBeTruthy();
    expect(screen.getByText("Looks right")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Update review" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change decision" }));
    expect(screen.getByRole("button", { name: "Update review" })).toBeTruthy();
  });
});

describe("StepGallery", () => {
  it("loads screenshots through the dashboard, never a storage path", () => {
    const { container } = render(
      <StepGallery
        auditId={AUDIT_ID}
        steps={[step(1), step(2, { has_evidence: false, status: "FAILED", analysis_status: "SKIPPED" })]}
        onOpenStep={vi.fn()}
      />,
    );
    const images = container.querySelectorAll("img");
    expect(images).toHaveLength(1);
    expect(images[0]?.getAttribute("src")).toBe(`/api/audits/${AUDIT_ID}/steps/1/screenshot`);
    expect(screen.getByText("No screenshot")).toBeTruthy();
    expect(screen.getByText(/Analysis: Skipped/)).toBeTruthy();
  });

  it("explains an empty list and a truncated page", () => {
    const { rerender } = render(<StepGallery auditId={AUDIT_ID} steps={[]} onOpenStep={vi.fn()} />);
    expect(screen.getByText("No steps captured yet.")).toBeTruthy();
    rerender(<StepGallery auditId={AUDIT_ID} steps={[step(1, { dom_truncated: true })]} onOpenStep={vi.fn()} />);
    expect(screen.getByText(/cut short/)).toBeTruthy();
  });
});

describe("NewAuditForm", () => {
  it("refuses an empty address without calling the server", () => {
    render(<NewAuditForm />);
    fireEvent.click(screen.getByRole("button", { name: "Start audit" }));
    expect(screen.getByRole("alert").textContent).toContain("Enter a website address");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("starts an audit and opens it", async () => {
    fetchMock.mockResolvedValue(json({ session_id: AUDIT_ID, status: "QUEUED" }, 202));
    render(<NewAuditForm />);
    fireEvent.change(screen.getByLabelText("Website address"), { target: { value: " https://shop.example.com " } });
    fireEvent.click(screen.getByRole("button", { name: "Start audit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/audits/${AUDIT_ID}`));
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({
      url: "https://shop.example.com",
    });
  });

  it("shows why the backend refused the address", async () => {
    fetchMock.mockResolvedValue(json({ error: "Target host is not allowed." }, 422));
    render(<NewAuditForm />);
    fireEvent.change(screen.getByLabelText("Website address"), { target: { value: "http://localhost" } });
    fireEvent.click(screen.getByRole("button", { name: "Start audit" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("not allowed"));
    expect(push).not.toHaveBeenCalled();
  });
});

describe("AuditView", () => {
  const detail = (status: string, extra = {}) => ({
    audit: audit({ status, ...extra }),
    steps: [step(1)],
    findings: [finding(), finding({ id: "33333333-3333-4333-8333-333333333333", category: "FALSE_URGENCY", review_status: "REJECTED", reviewed_at: "2026-11-07T11:00:00Z", reviewer_reference: "Sam" })],
  });

  it("always shows the not-a-legal-verdict notice and the filter counts", () => {
    render(<AuditView initial={detail("COMPLETED")} />);
    expect(screen.getByText(/not legal verdicts/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "All (2)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pending (1)" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rejected (1)" }));
    expect(screen.getByRole("heading", { name: "False urgency" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Interface interference" })).toBeNull();
  });

  it("offers cancel only while the audit is active", () => {
    render(<AuditView initial={detail("RUNNING")} />);
    expect(screen.getByRole("button", { name: "Cancel audit" })).toBeTruthy();
    cleanup();
    render(<AuditView initial={detail("COMPLETED")} />);
    expect(screen.queryByRole("button", { name: "Cancel audit" })).toBeNull();
  });

  it("explains a step-limit stop in plain words", () => {
    render(<AuditView initial={detail("FAILED", { error_code: "STEP_LIMIT_EXCEEDED" })} />);
    expect(screen.getByText(/reached the step limit/)).toBeTruthy();
  });

  it("polls while running, shows new findings, and stops when it finishes", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(json({ ...detail("RUNNING"), findings: [finding()], steps: [step(1), step(2)] }))
      .mockResolvedValue(json({ ...detail("COMPLETED"), findings: [finding()], steps: [step(1), step(2)] }));
    render(<AuditView initial={{ ...detail("RUNNING"), findings: [], steps: [] }} />);
    expect(screen.getByText(/No findings yet/)).toBeTruthy();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/audits/${AUDIT_ID}`);
    expect(screen.getByRole("heading", { name: "Interface interference" })).toBeTruthy();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Cancel audit" })).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2); // finished: no more polling
  });

  it("does not poll a finished audit at all", async () => {
    vi.useFakeTimers();
    render(<AuditView initial={detail("COMPLETED")} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps a review made here even if a poll arrives with older data", async () => {
    vi.useFakeTimers();
    const reviewed = finding({ review_status: "CONFIRMED", reviewed_at: "2026-11-07T11:30:00Z", reviewer_reference: "Riya" });
    fetchMock.mockImplementation(async () => json({ ...detail("RUNNING"), findings: [finding()] }));
    render(<AuditView initial={{ ...detail("RUNNING"), findings: [reviewed] }} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.getByText("Confirmed")).toBeTruthy();
  });

  it("shows a quiet retry note when a poll fails, then recovers", async () => {
    vi.useFakeTimers();
    fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue(json(detail("RUNNING")));
    render(<AuditView initial={detail("RUNNING")} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.getByText(/retrying/)).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.queryByText(/retrying/)).toBeNull();
  });

  it("opens and closes the screenshot viewer", () => {
    const { container } = render(<AuditView initial={detail("COMPLETED")} />);
    fireEvent.click(screen.getAllByRole("button", { name: "View screenshot" })[0]!);
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector("img")?.getAttribute("src")).toBe(`/api/audits/${AUDIT_ID}/steps/1/screenshot`);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(container).toBeTruthy();
  });
});
