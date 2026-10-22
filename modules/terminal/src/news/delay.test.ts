import { describe, expect, it } from "vitest";
import { collectionStalled, delayText, expiryText, formatDuration, formatRange } from "./delay";

describe("formatRange", () => {
  it.each([
    [180, 300, "3–5 min"],
    [0, 60, "0–60 s"],
    [45, 200, "45 s – 3 min"],
    [7200, 9000, "2–2,5 h"],
    [4000, 5400, "67 min – 1,5 h"],
    [120, 120, "2 min"],
  ])("writes %is to %is as %s", (low, high, expected) => {
    expect(formatRange(low, high)).toBe(expected);
  });
});

describe("delayText", () => {
  const measured = { delayMinSeconds: 180, delayMaxSeconds: 300, delayUnmeasured: null } as const;

  it("shows the two bounds of a measured headline", () => {
    expect(delayText(measured)).toBe("3–5 min");
  });

  it.each([
    ["found_there", "zastany przy pierwszym pobraniu"],
    ["no_publish_time", "brak czasu publikacji"],
    ["publish_time_in_future", "zegar źródła przed naszym"],
  ] as const)("says why %s has no delay, and never shows a zero", (reason, words) => {
    const text = delayText({ delayMinSeconds: null, delayMaxSeconds: null, delayUnmeasured: reason });

    expect(text).toBe(words);
    expect(text).not.toMatch(/^0/);
  });
});

describe("formatDuration", () => {
  it("is a dash where a source has nothing measured", () => {
    expect(formatDuration(null)).toBe("—");
  });
});

describe("collectionStalled", () => {
  it("is true only when sources are declared and none of them is answering", () => {
    expect(collectionStalled([])).toBe(false);
    expect(collectionStalled([{ status: "stale" }, { status: "failing" }, { status: "pending" }])).toBe(true);
    expect(collectionStalled([{ status: "stale" }, { status: "ok" }])).toBe(false);
  });
});

describe("expiryText", () => {
  const now = new Date("2026-09-29T12:00:00Z");

  it("names a date ahead, and the next sweep for one already past", () => {
    expect(expiryText(new Date("2026-10-27T12:00:00Z"), now)).toMatch(/^zniknie /);
    expect(expiryText(new Date("2026-09-01T12:00:00Z"), now)).toBe("zniknie przy najbliższym czyszczeniu");
  });

  it("says nothing for a kept headline, which has no date", () => {
    expect(expiryText(null, now)).toBeNull();
  });
});
