import { describe, expect, it } from "vitest";
import type { NewsItem } from "./newsApi";
import { directionLabel, sortItems } from "./sort";

function item(id: string, overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    source: "s",
    externalId: id,
    publisher: "P",
    title: id,
    summary: "",
    content: "",
    url: null,
    publishedAt: new Date("2026-09-29T12:00:00Z"),
    firstSeenAt: new Date("2026-09-29T12:05:00Z"),
    delayMinSeconds: 0,
    delayMaxSeconds: 300,
    delayUnmeasured: null,
    keptAt: null,
    expiresAt: null,
    ...overrides,
  };
}

const ids = (items: NewsItem[]) => items.map((i) => i.externalId);

describe("sortItems", () => {
  const early = item("early", { publishedAt: new Date("2026-09-29T10:00:00Z"), firstSeenAt: new Date("2026-09-29T13:00:00Z"), delayMaxSeconds: 10800 });
  const late = item("late", { publishedAt: new Date("2026-09-29T12:00:00Z"), firstSeenAt: new Date("2026-09-29T12:01:00Z"), delayMaxSeconds: 60 });

  it("orders by publication and by first sight, which are different orders", () => {
    expect(ids(sortItems([early, late], "published", "desc"))).toEqual(["late", "early"]);
    expect(ids(sortItems([early, late], "seen", "desc"))).toEqual(["early", "late"]);
    expect(ids(sortItems([early, late], "seen", "asc"))).toEqual(["late", "early"]);
  });

  it("places an undated headline by when it was first seen", () => {
    const undated = item("undated", { publishedAt: null, firstSeenAt: new Date("2026-09-29T11:00:00Z") });

    expect(ids(sortItems([early, undated, late], "published", "desc"))).toEqual(["late", "undated", "early"]);
  });

  it("puts a headline with no delay last whichever way the list runs", () => {
    const unmeasured = item("none", { delayMaxSeconds: null, delayMinSeconds: null, delayUnmeasured: "found_there" });

    expect(ids(sortItems([unmeasured, early, late], "delay", "desc"))).toEqual(["early", "late", "none"]);
    expect(ids(sortItems([unmeasured, early, late], "delay", "asc"))).toEqual(["late", "early", "none"]);
  });

  it("keeps the order it was given for equals, and does not touch its input", () => {
    const a = item("a");
    const b = item("b");
    const input = [b, a];

    expect(ids(sortItems(input, "delay", "desc"))).toEqual(["b", "a"]);
    expect(ids(input)).toEqual(["b", "a"]);
  });
});

describe("directionLabel", () => {
  it("speaks of waits as longest and shortest, and of times as newest and oldest", () => {
    expect(directionLabel("delay", "desc")).toBe("↓ najdłużej");
    expect(directionLabel("published", "asc")).toBe("↑ najstarsze");
  });
});
