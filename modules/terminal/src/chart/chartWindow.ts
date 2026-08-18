import type { CandlestickData, LogicalRange, Time, UTCTimestamp } from "lightweight-charts";
import type { Bar, ChartFocusRequest, Resolution } from "../data/types";
import type { BarsRange } from "./indicators/useIndicators";

/**
 * How much of the axis a chart asks for, and where on it a given moment sits.
 *
 * Arithmetic over bars and ranges, with no chart object in sight — which is why it is
 * here and not in `Chart.tsx`: every one of these answers a question the effects there
 * ask ("does the series still cover this?", "how far back does this focus reach?"), and
 * each is worth reading on its own rather than in the middle of an effect.
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

/** The window indicators are computed over: what is on screen, widened by a margin, and
 *  never wider than `MAX_INDICATOR_SPAN_BARS` of the resolution's own candles.
 *
 *  Follows the viewport rather than the drawn series, and that is the whole point. The
 *  series after a focus jump runs from March to the live edge with a five-month hole in
 *  the middle; asking for indicators over *that* prices a request nobody wants and gets a
 *  refusal for it. What the operator is looking at is a screenful either way.
 *
 *  `visible` is null before the chart has a frame — the first draw, and every draw where
 *  the library has not answered yet. The newest candles are the honest guess there: it is
 *  where an unfocused chart opens. */
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
  // Never the forming candle. A window ending on it would move with every tick, and
  // moving the window is what asks the archive for a new answer — the one thing this
  // must not do while a candle is still being built ("na żywo" is a later stage; see
  // `useIndicators`). Ending on the bar that last settled is what `applyBar` always did.
  if (series[toIndex].forming && toIndex > fromIndex) toIndex -= 1;

  const to = series[toIndex].time;
  // Clamped in time, not in candle count: the count is what the module prices, and it
  // prices it as periods between two moments — so a window straddling the hole a jump
  // leaves in the series is enormous however few candles are actually in it.
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

/** The earliest moment a focus needs drawn before it can be shown in full, or null for
 *  one that names no moment at all (`lastBars`, which is always at the newest end and can
 *  only ever want *more* of what is already there).
 *
 *  Not simply `focus.from ?? focus.around`, which is what `reachesBack` asks: an
 *  `around`+`bars` focus is centred, so half its candles sit *before* the moment it names.
 *  Reading only as far back as `around` puts the target on the series' first bar, and a
 *  frame centred there is the one the operator asked for shifted half a screen right.
 *  Sized with `RESOLUTION_SECONDS`, which is an approximation — a generous one here, since
 *  reading a little too far back costs candles nobody looks at and reading too little
 *  costs the frame. */
export function focusNeedsBackTo(focus: ChartFocusRequest, resolution: Resolution): number | null {
  if (focus.from !== null) return focus.from;
  if (focus.around !== null && focus.bars !== null) {
    return focus.around - Math.ceil(focus.bars / 2) * RESOLUTION_SECONDS[resolution];
  }
  return null;
}

/** Whether the drawn series has *any* candle the requested fragment could show — the
 *  weaker condition checked once the pager has given up, since a fragment only partly
 *  reached is still a fragment worth showing (`terminal-chart` spec, "Kadr na fragment
 *  już narysowany" is the applied case; "Kadr na okres, którego archiwum nie ma" is the
 *  one this returns `false` for). */
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

/** The widest span, in candles, one indicator request may cover.
 *
 *  Indicators used to be computed over the whole drawn series, which was fine while the
 *  series was whatever the operator had panned through. It stopped being fine when a
 *  focus could jump five months back: market-data prices a request as
 *  candles×indicators against a ceiling of 200,000, and six months of MINUTE_5 with four
 *  averages on it asks for 211,000 — a 422, and a chart that draws candles with no
 *  indicators on them at all.
 *
 *  Chosen against that ceiling with room for the instances an operator actually stacks:
 *  five thousand candles carries forty of them and still fits. It is not a copy of the
 *  module's number — the module refuses for its own reasons and this is the terminal not
 *  asking absurd questions in the first place. */
export const MAX_INDICATOR_SPAN_BARS = 5_000;

/** How near the newest drawn bar counts as "standing at the live edge" — a resolution
 *  change on a chart sitting there keeps sitting there, rather than being nudged into
 *  history by however many bars a pan or a redraw happened to leave short of the exact
 *  last index. */
export const RIGHT_EDGE_SLACK_BARS = 3;

/** How many candles a resolution change shows, floor and ceiling — the same reasoning
 *  `agent-chart-navigation`'s `MIN_FOCUS_BARS`/`MAX_FOCUS_BARS` used for a chart focus:
 *  below the floor there is nothing readable, above the ceiling a mismatch between the
 *  old and the new interval (WEEK's month of candles read as MINUTE_5) would ask for a
 *  screen no operator can use anyway. */
export const MIN_VISIBLE_BARS = 10;
export const MAX_VISIBLE_BARS = 500;

/** A candle's nominal length, seconds — an approximation good enough to size a viewport
 *  around, never a claim about when a real session opens (`useOlderBars.ts` refuses to
 *  keep a table like this for that reason, and does not need to: it measures the window
 *  it asks for from the drawn series' own timestamps instead). This one only decides how
 *  many candles roughly fill the span the operator was looking at. */
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
