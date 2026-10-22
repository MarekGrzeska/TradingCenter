import { describe, expect, it } from "vitest";
import type { NewsItem } from "./api";
import { directionLabel, sortItems } from "./sort";

const at = (minute: number) => new Date(Date.UTC(2026, 8, 29, 10, minute));

function item(id: string, overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    source: "s",
    externalId: id,
    publisher: "P",
    title: id,
    summary: "",
    content: "",
    url: null,
    publishedAt: at(0),
    firstSeenAt: at(0),
    delayMinSeconds: null,
    delayMaxSeconds: null,
    delayUnmeasured: null,
    keptAt: null,
    expiresAt: null,
    ...overrides,
  };
}

const ids = (items: NewsItem[]) => items.map((i) => i.externalId);

describe("sortItems", () => {
  it("sorts published by publishedAt, falling back to firstSeenAt", () => {
    const items = [
      item("a", { publishedAt: at(5) }),
      item("b", { publishedAt: null, firstSeenAt: at(9) }),
      item("c", { publishedAt: at(1) }),
    ];
    expect(ids(sortItems(items, "published", "desc"))).toEqual(["b", "a", "c"]);
    expect(ids(sortItems(items, "published", "asc"))).toEqual(["c", "a", "b"]);
  });

  it("sorts seen by firstSeenAt", () => {
    const items = [item("a", { firstSeenAt: at(3) }), item("b", { firstSeenAt: at(7) })];
    expect(ids(sortItems(items, "seen", "desc"))).toEqual(["b", "a"]);
  });

  it("puts an unknown wait last in either direction", () => {
    const items = [
      item("none"),
      item("short", { delayMaxSeconds: 60 }),
      item("long", { delayMaxSeconds: 600 }),
    ];
    expect(ids(sortItems(items, "waited", "desc"))).toEqual(["long", "short", "none"]);
    expect(ids(sortItems(items, "waited", "asc"))).toEqual(["short", "long", "none"]);
  });

  it("keeps equals in their order and leaves the input alone", () => {
    const items = [item("a"), item("b"), item("c")];
    const before = ids(items);
    expect(ids(sortItems(items, "published", "desc"))).toEqual(["a", "b", "c"]);
    expect(ids(sortItems(items, "published", "asc"))).toEqual(["a", "b", "c"]);
    expect(ids(items)).toEqual(before);
  });
});

describe("directionLabel", () => {
  it("names the direction by what the key measures", () => {
    expect(directionLabel("published", "desc")).toBe("↓ newest");
    expect(directionLabel("seen", "asc")).toBe("↑ oldest");
    expect(directionLabel("waited", "desc")).toBe("↓ longest");
    expect(directionLabel("waited", "asc")).toBe("↑ shortest");
  });
});
