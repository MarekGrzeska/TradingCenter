/**
 * How the loaded headlines are ordered. The server's order is by publication; the operator may also want the
 * order this archive saw them in, or by how long each one waited. A headline with no delay goes last whichever
 * way the list runs: "no measurement" is neither the longest wait nor the shortest.
 */

import type { NewsItem } from "./newsApi";

export type SortKey = "published" | "seen" | "delay";
export type SortDirection = "desc" | "asc";

export const SORT_LABELS: Record<SortKey, string> = {
  published: "publikacja",
  seen: "zobaczone",
  delay: "czekaliśmy",
};

function valueOf(item: NewsItem, key: SortKey): number | null {
  switch (key) {
    case "published":
      // The moment the server orders by, so an undated headline sits where it was first seen.
      return (item.publishedAt ?? item.firstSeenAt).getTime();
    case "seen":
      return item.firstSeenAt.getTime();
    case "delay":
      return item.delayMaxSeconds;
  }
}

export function sortItems(
  items: readonly NewsItem[],
  key: SortKey,
  direction: SortDirection,
): NewsItem[] {
  const sign = direction === "desc" ? -1 : 1;
  return items
    .map((item, index) => ({ item, index, value: valueOf(item, key) }))
    .sort((a, b) => {
      if (a.value === null && b.value === null) return a.index - b.index;
      if (a.value === null) return 1;
      if (b.value === null) return -1;
      return sign * (a.value - b.value) || a.index - b.index;
    })
    .map(({ item }) => item);
}

/** What the direction button says, since "newest" means nothing for a wait. */
export function directionLabel(key: SortKey, direction: SortDirection): string {
  if (key === "delay") return direction === "desc" ? "↓ najdłużej" : "↑ najkrócej";
  return direction === "desc" ? "↓ najnowsze" : "↑ najstarsze";
}
