import type { Bar } from "../data/types";
import type { DrawnInstance } from "./chartLines";
import type { ChartColors } from "./theme";

/**
 * What the crosshair is standing on, in numbers — the bar itself and every indicator
 * line's value at it.
 *
 * Its own module rather than part of `ChartReadout.tsx`: this is arithmetic over a list
 * of results, testable without rendering anything, and the components beside it are the
 * opposite.
 */

/** The bar the readout is answering for. */
export interface Readout {
  bar: Bar;
  /** True when this is the hovered bar rather than the latest one. */
  hovered: boolean;
}

export interface IndicatorReadoutEntry {
  key: string;
  /** The catalogue id this line belongs to (`sma`, `macd`, …) — several instances of
   *  one id are grouped onto one row; a different id always starts a row of its own. */
  id: string;
  label: string;
  value: number | null;
  /** The colour the line is drawn in. Two instances of one entry with the same params
   *  carry the same label, and then the swatch is the only thing that says which line a
   *  number came from (`terminal-chart` spec, "Wykres podaje wartości wskaźników spod
   *  kursora"). */
  color: string;
}

/**
 * The indicator values for whichever bar `OhlcReadout` is already showing — the same
 * bar the OHLC fields answer for, found by matching time rather than index, since a
 * indicator's own axis can start later than the candle series (`warmup_from`).
 *
 * Not hovering falls back to the newest bar (`shown.hovered` false — see `shown`'s own
 * computation), which is very often the one still forming: indicators are computed over
 * `redraw`'s own range and do not refetch on every live tick, so the exact instant just
 * traded is routinely a beat ahead of what the archive has answered for. Reading the
 * newest *answered* instant instead of returning nothing here is what keeps this text
 * matching the line already drawn on the chart, rather than blinking out every time the
 * pointer leaves it — a bar the operator is deliberately pointing at gets no such
 * fallback: an indicator with nothing to say about it says so.
 *
 * `drawn`/`lineColors` come in precomputed (memoized on the selections/results/colours
 * that actually change them) rather than recomputed here — `shown` moves on every
 * crosshair pixel, and neither `drawnInstances` nor `assignLineColors` needs to run
 * that often.
 */
export function activeIndicatorReadout(
  shown: Readout,
  times: number[],
  drawn: DrawnInstance[],
  lineColors: Map<string, string[]>,
  colors: ChartColors,
): IndicatorReadoutEntry[] {
  let index = times.indexOf(shown.bar.time);
  if (index === -1) {
    if (shown.hovered) return [];
    index = times.length - 1;
  }
  if (index === -1) return [];

  const entries: IndicatorReadoutEntry[] = [];
  for (const { selection, result, entry } of drawn) {
    if (!result.lines) continue;
    const assigned = lineColors.get(selection.key) ?? colors.indicatorLines;
    entry.lines.forEach((lineSpec, lineIndex) => {
      entries.push({
        key: `${selection.key}|${lineSpec.key}`,
        id: selection.id,
        label: fillLabelTemplate(lineSpec.label, result.params),
        value: result.lines?.[lineSpec.key]?.[index] ?? null,
        color: assigned[lineIndex],
      });
    });
  }
  return entries;
}

/** One row per catalogue id, in the order its first instance was drawn — several SMAs
 *  belong on one row together, a different indicator always starts its own. */
export function groupReadoutByIndicator(entries: IndicatorReadoutEntry[]): IndicatorReadoutEntry[][] {
  const byId = new Map<string, IndicatorReadoutEntry[]>();
  for (const entry of entries) {
    const group = byId.get(entry.id);
    if (group) group.push(entry);
    else byId.set(entry.id, [entry]);
  }
  return [...byId.values()];
}

function fillLabelTemplate(template: string, params: Record<string, number>): string {
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
