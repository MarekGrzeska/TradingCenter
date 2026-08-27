import { TickMarkType } from "lightweight-charts";
import { describe, expect, it } from "vitest";
import {
  formatBytes,
  formatCrosshairTime,
  formatInstant,
  formatTickMark,
  todayInWarsaw,
  warsawMidnightEpochSeconds,
} from "./formatTime";

// Built from `Date.UTC`, not hand-arithmetic on epoch seconds — a wrong constant here
// would make every assertion below check itself rather than the code under test.
const SUMMER = Date.UTC(2026, 7, 10, 14, 10, 0) / 1000; // 2026-08-10 14:10 UTC
const WINTER = Date.UTC(2026, 0, 10, 14, 10, 0) / 1000; // 2026-01-10 14:10 UTC
// Still 2026-08-10 in UTC, already 2026-08-11 in Warsaw (summer, UTC+2).
const CROSSING = Date.UTC(2026, 7, 10, 23, 30, 0) / 1000;

describe("formatInstant", () => {
  it("shows CEST in summer", () => {
    expect(formatInstant(SUMMER)).toBe("2026-08-10 16:10 CEST");
  });

  it("shows CET in winter", () => {
    expect(formatInstant(WINTER)).toBe("2026-01-10 15:10 CET");
  });

  it("crosses into the next Warsaw day before UTC does", () => {
    // The bug a formatter reading the process's own default zone (UTC in CI) instead of an explicit `Europe/Warsaw`
    // would show: this instant's UTC calendar day is still the 10th.
    expect(formatInstant(CROSSING)).toBe("2026-08-11 01:30 CEST");
  });
});

describe("formatBytes", () => {
  it("stays in bytes under 1 KB", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("switches to KB, then MB", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(1193376)).toBe("1.1 MB");
  });
});

describe("formatCrosshairTime", () => {
  it("names the day, month, year and Warsaw time together", () => {
    expect(formatCrosshairTime(SUMMER)).toBe("10 Aug 2026 16:10");
  });
});

describe("formatTickMark", () => {
  it("gives each grain its own shape, all in Warsaw time", () => {
    expect(formatTickMark(SUMMER, TickMarkType.Year)).toBe("2026");
    expect(formatTickMark(SUMMER, TickMarkType.Month)).toBe("10 Aug");
    expect(formatTickMark(SUMMER, TickMarkType.DayOfMonth)).toBe("10 Aug");
    expect(formatTickMark(SUMMER, TickMarkType.Time)).toBe("16:10");
  });

  it("crosses into the next Warsaw day before UTC does", () => {
    expect(formatTickMark(CROSSING, TickMarkType.DayOfMonth)).toBe("11 Aug");
  });
});

describe("warsawMidnightEpochSeconds", () => {
  it("lands the picked day's midnight one hour behind UTC in winter", () => {
    expect(warsawMidnightEpochSeconds("2026-01-10")).toBe(
      Date.parse("2026-01-09T23:00:00Z") / 1000,
    );
  });

  it("lands the picked day's midnight two hours behind UTC in summer", () => {
    expect(warsawMidnightEpochSeconds("2026-07-10")).toBe(
      Date.parse("2026-07-09T22:00:00Z") / 1000,
    );
  });

  it("round-trips with todayInWarsaw's own shape", () => {
    expect(() => warsawMidnightEpochSeconds(todayInWarsaw())).not.toThrow();
  });
});
