import { describe, expect, it } from "vitest";
import type { Post } from "./api";
import { headline, splitByImpact, toneFor } from "./impact";

function post(externalId: string, impactScore: number | null): Post {
  return {
    source: "truth_social",
    externalId,
    content: "TARIFFS.",
    translatedContent: null,
    url: null,
    isRepost: false,
    publishedAt: new Date("2026-08-31T10:00:00Z"),
    topics: [],
    impactScore,
    analysedModel: impactScore === null ? null : "an-analyst",
  };
}

describe("splitByImpact", () => {
  it("opens on what a model scored at or above the threshold", () => {
    const { high, rest } = splitByImpact([post("a", 9), post("b", 6), post("c", 5)]);

    expect(high.map((p) => p.externalId)).toEqual(["a", "b"]);
    expect(rest.map((p) => p.externalId)).toEqual(["c"]);
  });

  it("folds an unread post away rather than promoting it", () => {
    const { high, rest } = splitByImpact([post("unread", null)]);

    expect(high).toEqual([]);
    expect(rest.map((p) => p.externalId)).toEqual(["unread"]);
  });
});

describe("toneFor", () => {
  it("separates the three bands a score can be in", () => {
    expect(toneFor(9)).toBe("warn");
    expect(toneFor(5)).toBe("ok");
    expect(toneFor(2)).toBe("muted");
  });
});

describe("headline", () => {
  it("takes the first line and marks a cut", () => {
    expect(headline("first line\nsecond line")).toBe("first line");
    expect(headline("x".repeat(200))).toHaveLength(91);
  });
});
