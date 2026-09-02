import { describe, expect, it } from "vitest";

import { dispatchTokenValid } from "../src/clock";
import { commissioningAuthorized } from "../src/commission";
import { nextNominalSlotAfter, nominalSlotAt } from "../src/schedule";

describe("hourly slot calculation", () => {
  it("uses the current :17 slot after minute 17", () => {
    const now = Date.parse("2026-09-02T13:42:00Z");
    expect(new Date(nominalSlotAt(now)).toISOString()).toBe("2026-09-02T13:17:00.000Z");
    expect(new Date(nextNominalSlotAfter(now)).toISOString()).toBe("2026-09-02T14:17:00.000Z");
  });

  it("uses only one current slot after a multi-hour delay", () => {
    const delayed = Date.parse("2026-09-02T13:42:00Z");
    const nominal = nominalSlotAt(delayed);
    expect(nominal).not.toBe(Date.parse("2026-09-02T10:17:00Z"));
    expect(nextNominalSlotAfter(delayed) - nominal).toBe(60 * 60 * 1000);
  });

  it("uses the prior hour before minute 17", () => {
    const now = Date.parse("2026-09-02T13:02:00Z");
    expect(new Date(nominalSlotAt(now)).toISOString()).toBe("2026-09-02T12:17:00.000Z");
  });
});

describe("commissioning authentication", () => {
  const secret = "a-long-test-only-commissioning-secret";

  it("fails closed when the secret binding is missing", () => {
    const request = new Request("https://clock.example", {
      headers: { Authorization: "Bearer undefined" },
    });
    expect(commissioningAuthorized(request, undefined)).toBe(false);
  });

  it("accepts only an exact sufficiently long bearer secret", () => {
    const request = new Request("https://clock.example", {
      headers: { Authorization: `Bearer ${secret}` },
    });
    expect(commissioningAuthorized(request, secret)).toBe(true);
    expect(commissioningAuthorized(request, "wrong")).toBe(false);
  });
});

describe("dispatch credential validation", () => {
  it("fails closed for absent and short values", () => {
    expect(dispatchTokenValid(undefined)).toBe(false);
    expect(dispatchTokenValid("too-short")).toBe(false);
    expect(dispatchTokenValid("a-sufficiently-long-test-secret")).toBe(true);
  });
});
