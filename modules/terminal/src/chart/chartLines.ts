import { indicatorColorFromToken, indicatorLineColor, type ChartColors } from "./theme";
import type {
  IndicatorCatalogueEntry,
  IndicatorResult,
  IndicatorSelection,
} from "../data/types";

/**
 * Which indicator instances this chart can draw, and in what colours. Pure, and out of `Chart.tsx` for
 * that reason: a chart that computed these twice would eventually compute them differently.
 */

/**
 * A predicate rather than a filter on the catalogue: the picker still lists everything the archive offers,
 * and this only decides what may currently be picked. Every shape that draws today is price-pane only.
 */
export function canDrawIndicator(entry: IndicatorCatalogueEntry): boolean {
  if (entry.output === "lines") {
    return entry.render.pane === "price" || entry.render.pane === "own";
  }
  if (entry.output === "markers" || entry.output === "levels" || entry.output === "zones") {
    return entry.render.pane === "price";
  }
  return false;
}

/** One chosen instance beside the answer it got. The pairing is positional — the archive
 *  answers specs in the order they were asked for — because nothing on the wire tells two
 *  instances of one entry apart when their params agree. */
export interface DrawnInstance {
  selection: IndicatorSelection;
  result: IndicatorResult;
  entry: IndicatorCatalogueEntry;
}

/** The instances this chart can actually draw right now, zipped with their answers.
 *  A result carrying a reason carries no shape and is dropped here rather than at each
 *  branch below: "drew nothing" and "had nothing to draw" arriving at the same place by
 *  accident is how the next shape added quietly draws an empty one. */
export function drawnInstances(
  selections: IndicatorSelection[],
  results: IndicatorResult[],
  catalogueById: Map<string, IndicatorCatalogueEntry>,
): DrawnInstance[] {
  const drawn: DrawnInstance[] = [];
  selections.forEach((selection, index) => {
    const result = results[index];
    if (!result || result.error !== null) return;
    const entry = catalogueById.get(selection.id);
    if (!entry || !canDrawIndicator(entry)) return;
    drawn.push({ selection, result, entry });
  });
  return drawn;
}

/**
 * A colour per line of every drawn instance, in one pass. The cycle index is fixed by draw order alone, never
 * by which colours are already claimed by hand, so choosing one repaints that instance's own lines and no more.
 */
export function assignLineColors(
  drawn: DrawnInstance[],
  colors: ChartColors,
  chosenByKey: Map<string, string | null>,
): Map<string, string[]> {
  const chosen = new Map<string, string | null>();
  for (const { selection } of drawn) {
    // `has`, not `??`: null is the operator choosing *no* colour, and falling through on null would make
    // "Auto" a no-op for an instance restored with a colour.
    const token = chosenByKey.has(selection.key)
      ? (chosenByKey.get(selection.key) ?? null)
      : selection.color;
    chosen.set(selection.key, indicatorColorFromToken(colors, token));
  }

  const byKey = new Map<string, string[]>();
  let cycle = 0;
  for (const { selection, entry } of drawn) {
    const own = chosen.get(selection.key) ?? null;
    // A markers/levels/zones entry declares no lines and still needs one colour.
    const lineCount = Math.max(entry.lines.length, 1);
    const assigned: string[] = [];
    for (let index = 0; index < lineCount; index += 1) {
      const cycled = indicatorLineColor(colors, cycle);
      cycle += 1;
      assigned.push(index === 0 && own !== null ? own : cycled);
    }
    byKey.set(selection.key, assigned);
  }
  return byKey;
}
