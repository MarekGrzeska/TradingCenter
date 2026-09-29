/**
 * How a delay is written. Two numbers, never one: the lower bound is how late the feed was, the upper what the
 * operator waited, and what separates them is this archive's own polling. A headline that cannot be measured says
 * why instead of showing a zero.
 */

import type { NewsItem, NewsSource, SourceStatus, Unmeasured } from "./newsApi";

interface Amount {
  value: number;
  unit: "s" | "min" | "h";
}

function amount(seconds: number): Amount {
  if (seconds < 90) return { value: Math.round(seconds), unit: "s" };
  if (seconds < 90 * 60) return { value: Math.round(seconds / 60), unit: "min" };
  return { value: Math.round((seconds / 3600) * 10) / 10, unit: "h" };
}

function text({ value, unit }: Amount): string {
  return `${String(value).replace(".", ",")} ${unit}`;
}

/** "3–5 min" where both ends share a unit, "45 s – 3 min" where they do not. */
export function formatRange(lowSeconds: number, highSeconds: number): string {
  const low = amount(lowSeconds);
  const high = amount(highSeconds);
  if (low.unit === high.unit) {
    return low.value === high.value
      ? text(low)
      : `${String(low.value).replace(".", ",")}–${text(high)}`;
  }
  return `${text(low)} – ${text(high)}`;
}

export function formatDuration(seconds: number | null): string {
  return seconds === null ? "—" : text(amount(seconds));
}

const UNMEASURED: Record<Unmeasured, string> = {
  found_there: "zastany przy pierwszym pobraniu",
  no_publish_time: "brak czasu publikacji",
  publish_time_in_future: "zegar źródła przed naszym",
};

/** What a card shows in place of a delay. Never `0`, never an empty space. */
export function delayText(item: Pick<NewsItem, "delayMinSeconds" | "delayMaxSeconds" | "delayUnmeasured">): string {
  if (item.delayMinSeconds !== null && item.delayMaxSeconds !== null) {
    return formatRange(item.delayMinSeconds, item.delayMaxSeconds);
  }
  return item.delayUnmeasured === null ? "brak pomiaru" : UNMEASURED[item.delayUnmeasured];
}

export const STATUS_TEXT: Record<SourceStatus, string> = {
  ok: "działa",
  pending: "jeszcze nie pobrano",
  failing: "ostatnie pobranie nieudane",
  stale: "stoi",
};

/** Whether collection as a whole has stopped: sources are declared and none of them is answering. */
export function collectionStalled(sources: readonly Pick<NewsSource, "status">[]): boolean {
  return sources.length > 0 && sources.every((source) => source.status !== "ok");
}
