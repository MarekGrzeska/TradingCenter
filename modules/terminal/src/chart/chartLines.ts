import { indicatorColorFromToken, indicatorLineColor, type ChartColors } from "./theme";
import type {
  IndicatorCatalogueEntry,
  IndicatorResult,
  IndicatorSelection,
} from "../data/types";

/**
 * Which indicator instances this chart can draw, and in what colours.
 *
 * Pure, and out of `Chart.tsx` for that reason: the crosshair readout needs the same two
 * answers the drawing effect does, and a chart that computed them twice would eventually
 * compute them differently.
 */

/** Price-pane overlays, own-pane oscillators, price-pane markers, price-pane
 *  levels and price-pane zones all draw today. Every one of them is
 *  price-pane only because every entry the catalogue offers in those shapes
 *  draws on the candles, not in a pane of its own — `render.style ===
 *  "histogram"` on a `levels` entry (`time_profile`) still routes to
 *  `TimeProfilePrimitive` rather than `RayPrimitive` further down, but it is
 *  a *drawing* choice, not a *drawable* one, so it does not belong here.
 *  Kept as a predicate rather than a filter on the catalogue itself: the
 *  picker still lists every indicator the archive offers, this only decides
 *  which of them the operator may currently pick. */
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
 * A colour per line of every drawn instance, in one pass. An instance the operator gave a
 * colour spends it on its first line; its remaining lines (MACD's signal and histogram)
 * keep taking from the cycle, since three same-coloured lines in one pane say less than
 * three different ones.
 *
 * The cycle index is fixed by draw order alone, never by which colours are already claimed
 * by hand — matching `indicatorLines`' own invariant (theme.ts, "indexed by how many
 * indicator lines are already drawn — never by which one a line is"). Choosing a colour for
 * one instance can therefore only repaint that instance's own lines; it may occasionally
 * land on a hue a still-auto line already cycled onto, which a legend disambiguates.
 * Instances beyond the palette's eight repeat it, the way they always did.
 */
export function assignLineColors(
  drawn: DrawnInstance[],
  colors: ChartColors,
  chosenByKey: Map<string, string | null>,
): Map<string, string[]> {
  const chosen = new Map<string, string | null>();
  for (const { selection } of drawn) {
    // `has`, not `??`: null is the operator choosing *no* colour, and falling through to
    // the snapshot's own on null would make "Auto" a no-op for an instance restored with
    // a colour — it would keep painting the old one until the next recompute.
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
