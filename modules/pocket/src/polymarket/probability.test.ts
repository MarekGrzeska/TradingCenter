import { describe, expect, it } from "vitest";
import { bandFor, formatAge, formatChange, formatProbability, isStale } from "./probability";

describe("a probability on screen", () => {
  it("is a percentage, and the only place the scale changes", () => {
    expect(formatProbability(0.62)).toBe("62%");
    expect(formatProbability(1)).toBe("100%");
  });

  it("says nothing rather than zero when nothing has been collected", () => {
    expect(formatProbability(null)).toBe("—");
  });
});

describe("a change over a window", () => {
  it("is in points, with the unit said out loud", () => {
    expect(formatChange(0.021)).toBe("+2.1 pp");
    expect(formatChange(-0.021)).toBe("-2.1 pp");
  });

  it("is a dash when the collected history does not reach back that far", () => {
    expect(formatChange(null)).toBe("—");
  });
});

describe("the band a bar is coloured by", () => {
  it("belongs to the band an exact edge opens", () => {
    expect(bandFor(0.2)?.reading).toBe("leaning against");
    expect(bandFor(0.8)?.reading).toBe("likely");
  });

  it("is nothing at all without a price, rather than the lowest band", () => {
    expect(bandFor(null)).toBeNull();
  });
});

describe("how old a price is", () => {
  const now = new Date("2026-08-31T09:05:00Z");

  it("is stale past two of the archive's ticks", () => {
    expect(isStale(new Date("2026-08-31T09:04:00Z"), now)).toBe(false);
    expect(isStale(new Date("2026-08-31T09:02:00Z"), now)).toBe(true);
  });

  it("is stale when it cannot be dated at all", () => {
    expect(isStale(null, now)).toBe(true);
    expect(formatAge(null, now)).toBe("never");
  });

  it("is coarse, because the tick is a minute", () => {
    expect(formatAge(new Date("2026-08-31T09:04:30Z"), now)).toBe("just now");
    expect(formatAge(new Date("2026-08-31T08:45:00Z"), now)).toBe("20 min ago");
    expect(formatAge(new Date("2026-08-30T09:05:00Z"), now)).toBe("24 h ago");
  });
});
