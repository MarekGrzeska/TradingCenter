import { describe, expect, it } from "vitest";
import { bandOf, headline, splitByImpact } from "./impact";
import type { Post } from "./socialApi";

function post(externalId: string, impactScore: number | null): Post {
  return {
    source: "truth_social",
    externalId,
    author: "realDonaldTrump",
    content: "TARIFFS.",
    url: null,
    isRepost: false,
    publishedAt: new Date("2026-08-31T10:00:00Z"),
    translatedContent: null,
    topics: [],
    impactScore,
    analysedModel: impactScore === null ? null : "an-analyst",
    analysedAt: impactScore === null ? null : new Date(),
  };
}

describe("splitByImpact", () => {
  it("puts what a model scored at or above the threshold in front", () => {
    const { high, rest } = splitByImpact([post("a", 9), post("b", 6), post("c", 5)]);

    expect(high.map((p) => p.externalId)).toEqual(["a", "b"]);
    expect(rest.map((p) => p.externalId)).toEqual(["c"]);
  });

  it("folds away a post no model has read rather than promoting it", () => {
    // Unread is not unimportant, and it is not high impact either: the operator sees it
    // under the fold, where a low-scored post is.
    const { high, rest } = splitByImpact([post("unread", null)]);

    expect(high).toEqual([]);
    expect(rest.map((p) => p.externalId)).toEqual(["unread"]);
  });

  it("keeps the order it was given inside each half", () => {
    const { high } = splitByImpact([post("newer", 8), post("older", 7)]);

    expect(high.map((p) => p.externalId)).toEqual(["newer", "older"]);
  });
});

describe("bandOf", () => {
  it("separates unread from every score", () => {
    expect(bandOf(null)).toBe("unread");
    expect(bandOf(1)).toBe("low");
    expect(bandOf(4)).toBe("middling");
    expect(bandOf(7)).toBe("high");
  });
});

describe("headline", () => {
  it("takes the first line and marks a cut", () => {
    expect(headline("first line\nsecond line")).toBe("first line");
    expect(headline("x".repeat(200))).toHaveLength(121);
  });
});
