import { describe, expect, it } from "vitest";
import { formatAge, formatChange, formatProbability, isStale, STALE_AFTER_MS } from "./probability";

/** The lowest layer that holds the 0..1 rule, so it is tested here and not through the
 *  DOM. What the view does with these strings is the view's test. */

describe("formatProbability", () => {
  it("shows a 0..1 probability as a percentage, which is the one place it is multiplied", () => {
    expect(formatProbability(0.62)).toBe("62.0%");
    expect(formatProbability(1)).toBe("100.0%");
    expect(formatProbability(0)).toBe("0.0%");
  });

  it("answers null for an absent price rather than inventing a zero", () => {
    expect(formatProbability(null)).toBeNull();
  });
});

describe("formatChange", () => {
  it("is points, not percent — the two are confused exactly here", () => {
    // 0.60 → 0.62 is two points and also a rise of 3.3%. The unit is in the string
    // because a bare "+2.1%" would be the second claim carrying the first one's number.
    expect(formatChange(0.021)).toBe("+2.1 pp");
    expect(formatChange(-0.008)).toBe("−0.8 pp");
  });

  it("shows an actual standstill without a sign, and an absent one as null", () => {
    expect(formatChange(0)).toBe("0.0 pp");
    expect(formatChange(null)).toBeNull();
  });
});

describe("isStale", () => {
  const now = new Date("2026-08-22T12:00:00Z");

  it("holds a price fresh for twice the module's sampling tick", () => {
    expect(isStale(new Date(now.getTime() - STALE_AFTER_MS + 1_000), now)).toBe(false);
    expect(isStale(new Date(now.getTime() - STALE_AFTER_MS - 1_000), now)).toBe(true);
  });

  it("calls a price with no moment stale, because it cannot be vouched for", () => {
    expect(isStale(null, now)).toBe(true);
  });
});

describe("formatAge", () => {
  const now = new Date("2026-08-22T12:00:00Z");

  it("stays coarse, because the tick is a minute and seconds would only flicker", () => {
    expect(formatAge(new Date(now.getTime() - 30_000), now)).toBe("just now");
    expect(formatAge(new Date(now.getTime() - 40 * 60_000), now)).toBe("40 min ago");
    expect(formatAge(new Date(now.getTime() - 5 * 3_600_000), now)).toBe("5 h ago");
    expect(formatAge(new Date(now.getTime() - 4 * 86_400_000), now)).toBe("4 d ago");
  });

  it("answers null when there is no moment to age", () => {
    expect(formatAge(null, now)).toBeNull();
  });
});
