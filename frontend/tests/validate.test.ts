import { describe, expect, it } from "vitest";

import { categoryLabel } from "@/lib/categories";
import {
  errorNote,
  formatConfidence,
  formatDateTime,
  formatDuration,
  statusLabel,
} from "@/lib/format";
import { isUuid, parseStepNumber } from "@/lib/ids";
import { parseAuditUrl, parseReviewInput } from "@/lib/validate";

describe("parseReviewInput", () => {
  it("accepts and tidies a valid review", () => {
    expect(parseReviewInput({ decision: "CONFIRMED", reviewer: "  Riya ", notes: "  seen  " })).toEqual({
      ok: true,
      value: { decision: "CONFIRMED", reviewer: "Riya", notes: "seen" },
    });
  });

  it("turns blank or missing notes into no notes", () => {
    for (const notes of [undefined, null, "", "   "]) {
      const result = parseReviewInput({ decision: "REJECTED", reviewer: "R", notes });
      expect(result.ok && result.value.notes).toBeUndefined();
    }
  });

  it.each([
    ["not an object", null],
    ["a string", "x"],
    ["PENDING_REVIEW as a decision", { decision: "PENDING_REVIEW", reviewer: "R" }],
    ["a lowercase decision", { decision: "confirmed", reviewer: "R" }],
    ["no decision", { reviewer: "R" }],
    ["no reviewer", { decision: "CONFIRMED" }],
    ["a blank reviewer", { decision: "CONFIRMED", reviewer: "   " }],
    ["a reviewer with a newline", { decision: "CONFIRMED", reviewer: "a\nb" }],
    ["a reviewer with a control character", { decision: "CONFIRMED", reviewer: "a\u0007b" }],
    ["a too-long reviewer", { decision: "CONFIRMED", reviewer: "x".repeat(81) }],
    ["too-long notes", { decision: "CONFIRMED", reviewer: "R", notes: "n".repeat(2001) }],
    ["non-string notes", { decision: "CONFIRMED", reviewer: "R", notes: 5 }],
  ])("refuses %s", (_label, input) => {
    expect(parseReviewInput(input).ok).toBe(false);
  });

  it("allows exactly the limits", () => {
    expect(parseReviewInput({ decision: "INCONCLUSIVE", reviewer: "x".repeat(80), notes: "n".repeat(2000) }).ok).toBe(true);
  });
});

describe("parseAuditUrl", () => {
  it("trims and accepts an address", () => {
    expect(parseAuditUrl("  https://shop.example.com ")).toEqual({ ok: true, value: "https://shop.example.com" });
  });
  it("refuses empty, non-text and over-long input", () => {
    for (const bad of ["", "   ", 5, null, "h".repeat(2049)]) expect(parseAuditUrl(bad).ok).toBe(false);
  });
});

describe("ids", () => {
  it("accepts only real UUIDs", () => {
    expect(isUuid("11111111-1111-4111-8111-111111111111")).toBe(true);
    for (const bad of ["", "abc", "11111111-1111-4111-8111-11111111111", 5, null, "../x"]) {
      expect(isUuid(bad)).toBe(false);
    }
  });
  it("accepts only whole step numbers from 1 to 1000", () => {
    expect(parseStepNumber("1")).toBe(1);
    expect(parseStepNumber("1000")).toBe(1000);
    for (const bad of ["0", "1001", "-1", "1.5", "abc", "", "01a", " 1", 1]) {
      expect(parseStepNumber(bad)).toBeNull();
    }
  });
});

describe("formatting", () => {
  it("labels the 13 categories and falls back for unknown ones", () => {
    expect(categoryLabel("FALSE_URGENCY")).toBe("False urgency");
    expect(categoryLabel("SAAS_BILLING")).toBe("SaaS billing");
    expect(categoryLabel("SOMETHING_NEW")).toBe("Something new");
    expect(categoryLabel("")).toBe("Unknown");
  });

  it("formats confidence, clamped to 0-100%", () => {
    expect(formatConfidence(0.854)).toBe("85%");
    expect(formatConfidence(2)).toBe("100%");
    expect(formatConfidence(-1)).toBe("0%");
    expect(formatConfidence(Number.NaN)).toBe("-");
  });

  it("formats times and durations safely", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime("garbage")).toBe("-");
    expect(formatDateTime("2026-11-07T10:00:00Z")).toContain("UTC");
    expect(formatDuration("2026-11-07T10:00:00Z", "2026-11-07T10:01:35Z")).toBe("1m 35s");
    expect(formatDuration("2026-11-07T10:00:00Z", "2026-11-07T10:00:09Z")).toBe("9s");
    expect(formatDuration(null, "2026-11-07T10:00:09Z")).toBe("-");
    expect(formatDuration("2026-11-07T10:00:09Z", "2026-11-07T10:00:00Z")).toBe("-");
  });

  it("explains known error codes and falls back to the backend message", () => {
    expect(errorNote(null, null)).toBeNull();
    expect(errorNote("STEP_LIMIT_EXCEEDED", null)).toContain("step limit");
    expect(errorNote("PARTIAL_RESULTS", "x")).toContain("not fully analysed");
    expect(errorNote("WEIRD", "Backend said this")).toBe("Backend said this");
    expect(errorNote("WEIRD", null)).toContain("did not finish");
    expect(statusLabel("PENDING_REVIEW")).toBe("Pending review");
  });
});
