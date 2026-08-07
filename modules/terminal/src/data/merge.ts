import type { Bar } from "./types";

/**
 * Merge one incoming bar into a series sorted ascending by `time`, with no two
 * bars sharing a timestamp. Three cases, in order of how often they happen:
 *
 *  - matches the last bar's time → replaces it (the common case: the forming
 *    candle changing, or a settled candle superseding it)
 *  - later than the last bar's time → appended (a new period opened)
 *  - anything else (history-gap backfill after a reconnect, or an out-of-order
 *    arrival) → located by binary search and replaced or inserted in place
 *
 * Pure and allocation-light on the hot path: the first two cases, which cover
 * every live tick, touch only the tail of the array.
 */
export function mergeBar(series: readonly Bar[], incoming: Bar): Bar[] {
  const len = series.length;
  if (len === 0) {
    return [incoming];
  }

  const last = series[len - 1];
  if (incoming.time === last.time) {
    return [...series.slice(0, -1), incoming];
  }
  if (incoming.time > last.time) {
    return [...series, incoming];
  }

  const index = lowerBound(series, incoming.time);
  if (index < len && series[index].time === incoming.time) {
    const next = series.slice();
    next[index] = incoming;
    return next;
  }
  const next = series.slice();
  next.splice(index, 0, incoming);
  return next;
}

/** Fold `mergeBar` over many incoming bars — history merged with a reconnect's
 *  gap-fill, or a batch of history pages joined in order. */
export function mergeSeries(base: readonly Bar[], incoming: readonly Bar[]): Bar[] {
  let result: Bar[] = base as Bar[];
  for (const bar of incoming) {
    result = mergeBar(result, bar);
  }
  return result;
}

/** The bar at exactly `time`, or undefined. Binary search — the chart calls
 *  this on every crosshair move, over a series of several hundred bars. */
export function findBar(series: readonly Bar[], time: number): Bar | undefined {
  const index = lowerBound(series, time);
  const found = series[index];
  return found?.time === time ? found : undefined;
}

/** Index of the first bar whose `time` is >= `time`, or `series.length` if none. */
function lowerBound(series: readonly Bar[], time: number): number {
  let lo = 0;
  let hi = series.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (series[mid].time < time) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}
