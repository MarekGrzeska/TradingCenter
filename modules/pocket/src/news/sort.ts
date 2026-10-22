import type { NewsItem } from "./api";

export type SortKey = "published" | "seen" | "waited";
export type SortDirection = "desc" | "asc";

/** An unknown wait (`null`) goes last in both directions, so "longest" never opens with a blank. */
export function sortItems(items: readonly NewsItem[], key: SortKey, direction: SortDirection): NewsItem[] {
  const sign = direction === "desc" ? -1 : 1;
  const value = (item: NewsItem): number | null =>
    key === "waited"
      ? item.delayMaxSeconds
      : (key === "seen" ? item.firstSeenAt : (item.publishedAt ?? item.firstSeenAt)).getTime();
  return [...items].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    return sign * (x - y);
  });
}

export function directionLabel(key: SortKey, direction: SortDirection): string {
  if (key === "waited") return direction === "desc" ? "↓ longest" : "↑ shortest";
  return direction === "desc" ? "↓ newest" : "↑ oldest";
}
