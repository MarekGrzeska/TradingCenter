import { describe, expect, it } from "vitest";
import { nextCalendarDay, toUsageRange } from "./dateRange";

describe("nextCalendarDay", () => {
  it("steps a plain day forward", () => {
    expect(nextCalendarDay("2026-08-11")).toBe("2026-08-12");
  });

  it("carries a month boundary", () => {
    expect(nextCalendarDay("2026-08-31")).toBe("2026-09-01");
  });

  it("carries a year boundary", () => {
    expect(nextCalendarDay("2026-12-31")).toBe("2027-01-01");
  });

  it("carries a leap day correctly", () => {
    expect(nextCalendarDay("2028-02-28")).toBe("2028-02-29");
    expect(nextCalendarDay("2028-02-29")).toBe("2028-03-01");
  });
});

describe("toUsageRange", () => {
  it("makes the picked `to` day fully inside the range, not the boundary", () => {
    const { from, to } = toUsageRange({ from: "2026-08-01", to: "2026-08-11" });
    // Any instant on 2026-08-11, Warsaw time, must fall inside [from, to).
    const middleOfToDay = Date.parse("2026-08-11T20:00:00+02:00") / 1000;
    expect(from).toBeLessThanOrEqual(Date.parse("2026-08-01T00:00:00+02:00") / 1000);
    expect(middleOfToDay).toBeGreaterThanOrEqual(from);
    expect(middleOfToDay).toBeLessThan(to);
    // And the instant right after `to` — the following day — must fall outside it.
    expect(Date.parse("2026-08-12T00:30:00+02:00") / 1000).toBeGreaterThanOrEqual(to);
  });
});
