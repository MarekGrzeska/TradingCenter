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

/**
 * Two series into one, sorted by `time`, with no duplicate timestamp — a reconnect's
 * gap-fill folded into what is drawn, or a page of older candles joined to the front.
 * Where both carry the same period, `incoming` wins.
 *
 * A single linear pass, not `mergeBar` per bar. That fold copies the whole array for
 * every incoming candle, which is nothing for a gap-fill of three and several million
 * element copies for a 300-candle page merged into a series of thousands — felt as a
 * stutter every time the chart paged history in.
 */
export function mergeSeries(base: readonly Bar[], incoming: readonly Bar[]): Bar[] {
  if (incoming.length === 0) return base as Bar[];
  if (base.length === 0) return sorted(incoming);

  const right = sorted(incoming);
  const result: Bar[] = [];
  let i = 0;
  let j = 0;

  while (i < base.length && j < right.length) {
    const left = base[i];
    const next = right[j];
    if (left.time < next.time) {
      result.push(left);
      i++;
    } else if (left.time > next.time) {
      result.push(next);
      j++;
    } else {
      result.push(next);
      i++;
      j++;
    }
  }
  while (i < base.length) result.push(base[i++]);
  while (j < right.length) result.push(right[j++]);
  return result;
}

/** `incoming` is sorted in practice — both a snapshot and a range read answer in order —
 *  but the merge is only linear if it is, so an out-of-order batch is put in order rather
 *  than trusted. Checking costs one pass and almost always finds nothing to do. */
function sorted(bars: readonly Bar[]): Bar[] {
  for (let index = 1; index < bars.length; index++) {
    if (bars[index - 1].time > bars[index].time) {
      return [...bars].sort((a, b) => a.time - b.time);
    }
  }
  return [...bars];
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
