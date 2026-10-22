import type { DelayUnmeasured, NewsItem } from "./api";

const REASONS: Record<DelayUnmeasured, string> = {
  found_there: "found on first fetch",
  no_publish_time: "no publish time",
  publish_time_in_future: "source clock ahead",
};

function unit(seconds: number): [number, string] {
  if (seconds < 60) return [Math.round(seconds), "s"];
  if (seconds < 3600) return [Math.round(seconds / 60), "min"];
  return [Math.round(seconds / 360) / 10, "h"];
}

/** `"3–5 min"`: the bounds share a unit when they have one, so the range reads as one figure. */
export function formatRange(min: number, max: number): string {
  const [lo, loUnit] = unit(min);
  const [hi, hiUnit] = unit(max);
  if (lo === hi && loUnit === hiUnit) return `${hi} ${hiUnit}`;
  return loUnit === hiUnit ? `${lo}–${hi} ${hiUnit}` : `${lo} ${loUnit}–${hi} ${hiUnit}`;
}

/** A measured range, or the reason there is none — the card never shows a bare zero or a blank. */
export function formatDelay(item: Pick<NewsItem, "delayMinSeconds" | "delayMaxSeconds" | "delayUnmeasured">): string {
  if (item.delayMinSeconds !== null && item.delayMaxSeconds !== null) {
    return formatRange(item.delayMinSeconds, item.delayMaxSeconds);
  }
  return item.delayUnmeasured === null ? "not measured" : REASONS[item.delayUnmeasured];
}

export function formatSourceDelay(median: number | null, p90: number | null): string {
  if (median === null || p90 === null) return "n/a";
  return `${formatRange(median, median)} / ${formatRange(p90, p90)}`;
}
