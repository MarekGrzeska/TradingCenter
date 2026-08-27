import type { Bar } from "../data/types";
import type { DrawnInstance } from "./chartLines";
import type { ChartColors } from "./theme";

/**
 * What the crosshair is standing on, in numbers — the bar itself and every indicator line's value at it.
 * Its own module: this is arithmetic over a list of results, testable without rendering anything.
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
 * Indicator values for the bar the readout shows, matched by time since an indicator's axis can start later.
 * Not hovering falls back to the newest answered instant, so the text stops blinking out when the pointer leaves.
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
