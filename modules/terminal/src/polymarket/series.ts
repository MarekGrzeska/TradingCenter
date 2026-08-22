import type { PricePoint } from "./polymarketApi";

/**
 * Turning a collected series into what a line chart may draw.
 *
 * The whole content is the gap. A line series joins consecutive points, so two readings
 * either side of a stretch that was never collected come out as a straight run between
 * them — a claim that the probability moved evenly across days nobody measured. The
 * library's own way of refusing to draw that is a **whitespace point**: a time with no
 * value, which breaks the line (specs/terminal-polymarket, "Seria prawdopodobieństwa jest
 * oglądalna wraz z granicą pokrycia").
 */

export interface LinePoint {
  time: number;
  value?: number;
}

/** How many times the series' own typical spacing counts as a gap.
 *
 *  Relative rather than absolute, and that is the measurement this file rests on: the
 *  module samples live prices once a minute, but backfilled history arrives at whatever
 *  resolution the provider gives for an old range, which is coarser and varies with the
 *  span asked for. A fixed threshold in minutes would call every backfilled series one
 *  long gap, or call nothing a gap at all, depending on the range the operator picked. */
const GAP_FACTOR = 3;

/** The middle spacing between consecutive points, or `null` for a series too short to
 *  have one. Median rather than mean: one real gap would drag a mean far enough to hide
 *  every other gap behind it. */
export function medianSpacing(points: PricePoint[]): number | null {
  if (points.length < 2) return null;
  const gaps: number[] = [];
  for (let i = 1; i < points.length; i++) {
    gaps.push(points[i].at.getTime() - points[i - 1].at.getTime());
  }
  gaps.sort((a, b) => a - b);
  const middle = Math.floor(gaps.length / 2);
  return gaps.length % 2 === 0 ? (gaps[middle - 1] + gaps[middle]) / 2 : gaps[middle];
}

/**
 * The series as the chart takes it: seconds since the epoch, and a whitespace point
 * wherever the collected history stops and starts again.
 *
 * A point whose price is `null` is itself a hole — the module recorded the moment and no
 * price for it — so it becomes whitespace rather than being dropped, which would let the
 * line close over it.
 */
export function toLineData(points: PricePoint[]): LinePoint[] {
  const threshold = medianSpacing(points);
  const data: LinePoint[] = [];

  points.forEach((point, index) => {
    const previous = points[index - 1];
    if (
      previous !== undefined &&
      threshold !== null &&
      point.at.getTime() - previous.at.getTime() > threshold * GAP_FACTOR
    ) {
      // Halfway between the two readings: the break belongs to the stretch nobody
      // measured, not to either of the moments that were.
      const midpoint = (previous.at.getTime() + point.at.getTime()) / 2;
      data.push({ time: Math.floor(midpoint / 1000) });
    }
    data.push(
      point.price === null
        ? { time: Math.floor(point.at.getTime() / 1000) }
        : { time: Math.floor(point.at.getTime() / 1000), value: point.price },
    );
  });

  return data;
}

export type RangeChoice = "7d" | "30d" | "90d" | "all";

export const RANGES: RangeChoice[] = ["7d", "30d", "90d", "all"];

const DAYS: Record<Exclude<RangeChoice, "all">, number> = { "7d": 7, "30d": 30, "90d": 90 };

/** Where a range starts, or `undefined` for "as far back as there is" — which the module
 *  answers with whatever it holds rather than with an error. */
export function rangeStart(range: RangeChoice, now: Date = new Date()): Date | undefined {
  if (range === "all") return undefined;
  return new Date(now.getTime() - DAYS[range] * 86_400_000);
}

/** Whether the operator asked for more history than was ever collected — which is when
 *  the boundary has to be drawn rather than left to be inferred from the line stopping. */
export function reachesBeforeCoverage(
  range: RangeChoice,
  collectedFrom: Date | null,
  now: Date = new Date(),
): boolean {
  if (collectedFrom === null) return false;
  const start = rangeStart(range, now);
  return start === undefined || start < collectedFrom;
}
