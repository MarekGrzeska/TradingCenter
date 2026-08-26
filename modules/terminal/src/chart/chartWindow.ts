import type { CandlestickData, LogicalRange, Time, UTCTimestamp } from "lightweight-charts";
import type { Bar, ChartFocusRequest, Resolution } from "../data/types";
import type { BarsRange } from "./indicators/useIndicators";

/**
 * How much of the axis a chart asks for, and where on it a moment sits — arithmetic over bars and ranges,
 * with no chart object in sight, each answer worth reading on its own rather than inside an effect.
 */

export function toCandlestick(bar: Bar): CandlestickData<Time> {
  return {
    time: bar.time as UTCTimestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
}

/** Index of the drawn bar closest to `time` — the anchor for an `around`+`bars` focus,
 *  which names a moment rather than a bar that necessarily exists at it (a session gap,
 *  most often). `findBar` (`data/merge.ts`) only ever answers an exact match, which this
 *  is deliberately not. */
export function nearestBarIndex(series: readonly Bar[], time: number): number {
  let lo = 0;
  let hi = series.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (series[mid].time < time) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(series[lo - 1].time - time) <= Math.abs(series[lo].time - time)) {
    return lo - 1;
  }
  return lo;
}

/** Whether the drawn series already reaches back far enough to show `focus` in full —
 *  the condition that lets a focus apply immediately, without waiting on the pager. */
export function reachesBack(series: readonly Bar[], focus: ChartFocusRequest): boolean {
  if (series.length === 0) return false;
  if (focus.lastBars !== null) return series.length >= focus.lastBars;
  const target = focus.from ?? focus.around;
  return target !== null && series[0].time <= target;
}

/**
 * The window indicators are computed over: the viewport widened by a margin, capped. The viewport rather than
 * the drawn series, which after a focus jump runs from March to the live edge with a five-month hole.
 */
export function indicatorWindow(
  series: readonly Bar[],
  visible: LogicalRange | null,
  resolution: Resolution,
): BarsRange | null {
  if (series.length === 0) return null;
  const lastIndex = series.length - 1;
  const rawFrom = visible === null ? lastIndex - MAX_INDICATOR_SPAN_BARS : Math.floor(visible.from);
  const rawTo = visible === null ? lastIndex : Math.ceil(visible.to);

  const fromIndex = Math.max(0, Math.min(lastIndex, rawFrom - INDICATOR_MARGIN_BARS));
  let toIndex = Math.max(fromIndex, Math.min(lastIndex, rawTo + INDICATOR_MARGIN_BARS));
  // Never the forming candle. A window ending on it would move with every tick, and moving the window is
  // what asks the archive for a new answer.
  if (series[toIndex].forming && toIndex > fromIndex) toIndex -= 1;

  const to = series[toIndex].time;
  // Clamped in time, not in candle count: the module prices a request as periods between two moments, so
  // a window straddling the hole a jump leaves is enormous however few candles are in it.
  const floor = to - MAX_INDICATOR_SPAN_BARS * RESOLUTION_SECONDS[resolution];
  return { from: Math.max(series[fromIndex].time, floor), to };
}

/** Whether `window` still covers what is on screen, margins excluded — the test for
 *  leaving a computed answer alone. Panning inside the margin changes the window this
 *  function is not asked about; panning out of it is what earns a new read. */
export function windowStillCovers(
  window: BarsRange,
  series: readonly Bar[],
  visible: LogicalRange | null,
): boolean {
  if (visible === null || series.length === 0) return true;
  const lastIndex = series.length - 1;
  const from = series[Math.max(0, Math.min(lastIndex, Math.floor(visible.from)))].time;
  const to = series[Math.max(0, Math.min(lastIndex, Math.ceil(visible.to)))].time;
  return from >= window.from && to <= window.to;
}

/** The earliest moment a focus needs drawn before it can be shown in full, or null for one that names no
 *  moment at all. Not simply `focus.from ?? focus.around`: an `around`+`bars` focus is centred, so half
 *  its candles sit before the moment it names, and reading only that far back shifts the frame. */
export function focusNeedsBackTo(focus: ChartFocusRequest, resolution: Resolution): number | null {
  if (focus.from !== null) return focus.from;
  if (focus.around !== null && focus.bars !== null) {
    return focus.around - Math.ceil(focus.bars / 2) * RESOLUTION_SECONDS[resolution];
  }
  return null;
}

/** Whether the drawn series has *any* candle the requested fragment could show — the weaker condition
 *  checked once the pager has given up, since a fragment only partly reached is still worth showing. */
export function overlapsSeries(series: readonly Bar[], focus: ChartFocusRequest): boolean {
  if (series.length === 0) return false;
  if (focus.lastBars !== null) return true;
  const oldest = series[0].time;
  const newest = series[series.length - 1].time;
  if (focus.from !== null && focus.to !== null) return newest >= focus.from && oldest <= focus.to;
  if (focus.around !== null) return newest >= focus.around;
  return false;
}

/** What the outgoing series' viewport looked like, captured the moment a resolution
 *  change is about to clear it — everything `redraw` needs to put the incoming series'
 *  first draw over the same stretch of time instead of the whole thing
 *  (`terminal-chart` spec, "Rozdzielczość zmienia się bez przeładowania"). */
export interface PendingResolutionFrame {
  from: number;
  to: number;
  /** Whether the outgoing view reached (within `RIGHT_EDGE_SLACK_BARS`) the newest drawn
   *  bar — the anchor a chart standing at the live edge keeps, rather than the span's own
   *  midpoint. */
  atRightEdge: boolean;
}

/** How few candles may be left to the viewport's left before older ones are
 *  fetched, counted in bars. It is both the trigger and the target: the pager
 *  keeps going until the viewport has at least this much history behind it, so
 *  one drag to the edge is answered with a screenful rather than a page. */
export const OLDER_MARGIN_BARS = 50;

/** How many candles either side of what is on screen the indicators are computed for.
 *  Ordinary panning then moves inside an answer already in hand rather than asking the
 *  archive for a new one on every drag. */
export const INDICATOR_MARGIN_BARS = 300;

/**
 * The widest span one indicator request may cover: six months of MINUTE_5 with four averages asks for 211,000
 * against the module's ceiling of 200,000. Not a copy of that number — this is not asking absurd questions.
 */
export const MAX_INDICATOR_SPAN_BARS = 5_000;

/** How near the newest drawn bar counts as "standing at the live edge" — a resolution
 *  change on a chart sitting there keeps sitting there, rather than being nudged into
 *  history by however many bars a pan or a redraw happened to leave short of the exact
 *  last index. */
export const RIGHT_EDGE_SLACK_BARS = 3;

/** How many candles a resolution change shows, floor and ceiling: below the floor there is nothing
 *  readable, above it a mismatch between the old and new interval asks for a screen nobody can use. */
export const MIN_VISIBLE_BARS = 10;
export const MAX_VISIBLE_BARS = 500;

/** A candle's nominal length, seconds — an approximation good enough to size a viewport around, never a
 *  claim about when a real session opens. It only decides how many candles roughly fill a span. */
export const RESOLUTION_SECONDS: Record<Resolution, number> = {
  MINUTE: 60,
  MINUTE_5: 300,
  MINUTE_15: 900,
  MINUTE_30: 1800,
  HOUR: 3600,
  HOUR_4: 14400,
  DAY: 86400,
  WEEK: 604800,
};
