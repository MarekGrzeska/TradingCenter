/**
 * The chart is a canvas — it cannot wear a Tailwind class, so it reads the same
 * `@theme` tokens `index.css` declares and hands them to lightweight-charts as
 * plain strings. One definition, both consumers: terminal-shell spec, "Motyw
 * jest ciemny i wyprowadzony z tokenów".
 *
 * Fallbacks exist because jsdom has no stylesheet: in tests `getPropertyValue`
 * returns "" and a chart built from empty color strings throws deep inside the
 * library rather than at the call site.
 */

const FALLBACKS: Record<string, string> = {
  "--color-panel": "#121620",
  "--color-ink": "#ffffff",
  "--color-ink-muted": "#8794a8",
  "--color-grid": "#1c2331",
  "--color-axis": "#2b3446",
  "--color-up": "#199e70",
  "--color-down": "#e66767",
  "--color-accent": "#3987e5",
  "--color-indicator-2": "#d95926",
  "--color-indicator-4": "#c98500",
  "--color-indicator-5": "#d55181",
  "--color-indicator-6": "#008300",
  "--color-indicator-7": "#9085e9",
  "--color-drawing-1": "#009fb4",
  "--color-drawing-2": "#8f5ada",
  "--color-drawing-3": "#7f9422",
  "--color-drawing-4": "#d14f72",
};

function token(styles: CSSStyleDeclaration | null, name: string): string {
  const value = styles?.getPropertyValue(name).trim();
  return value || FALLBACKS[name];
}

/**
 * This codebase's whole validated categorical palette, in the dataviz skill's
 * documented order — `--color-accent`, `--color-up` and `--color-down` included, at
 * the positions the palette validator's adjacent-pair check requires them at. Picking
 * any other subset or order failed that check (orange next to yellow, ΔE 4.8 — below
 * the CVD floor); reusing the full eight, unchanged, is what passes.
 */
export const INDICATOR_LINE_TOKENS = [
  "--color-accent",
  "--color-indicator-2",
  "--color-up",
  "--color-indicator-4",
  "--color-indicator-5",
  "--color-indicator-6",
  "--color-indicator-7",
  "--color-down",
] as const;

export type IndicatorColorToken = (typeof INDICATOR_LINE_TOKENS)[number];

export function isIndicatorColorToken(value: unknown): value is IndicatorColorToken {
  return typeof value === "string" && (INDICATOR_LINE_TOKENS as readonly string[]).includes(value);
}

/**
 * The objects an operator draws, in four hues none of the eight above uses — an object
 * that cannot be told from an indicator line is the reason this list exists at all
 * (`agent-chart-drawings` spec, "Paleta rysunków MUST być odrębna"). Four is not a
 * shortage: a drawing's colour is a function of its own id, so any two hues can meet on
 * one chart, and four is where the palette validator's all-pairs list still clears every
 * gate on this surface. See `index.css` for the measurements.
 */
export const DRAWING_LINE_TOKENS = [
  "--color-drawing-1",
  "--color-drawing-2",
  "--color-drawing-3",
  "--color-drawing-4",
] as const;

export type DrawingColorToken = (typeof DRAWING_LINE_TOKENS)[number];

export function isDrawingColorToken(value: unknown): value is DrawingColorToken {
  return typeof value === "string" && (DRAWING_LINE_TOKENS as readonly string[]).includes(value);
}

export interface ChartColors {
  surface: string;
  ink: string;
  inkMuted: string;
  grid: string;
  axis: string;
  up: string;
  down: string;
  /** Fixed order, indexed by how many indicator lines are already drawn — never by
   *  which one a line is, so adding or removing one never repaints another
   *  (dataviz skill, "Color follows the entity, never its rank"; here the order of
   *  appearance is the entity, since a line has no identity a legend names). Cycles
   *  past the eighth concurrent line rather than inventing a ninth hue. */
  indicatorLines: readonly string[];
  /** Fixed order, indexed by the drawing's own id rather than by anything about the
   *  chart it stands on — which is the whole difference from `indicatorLines` above
   *  (`terminal-chart` spec, "Kolor obiektu po usunięciu innego"). */
  drawingLines: readonly string[];
}

export function readChartColors(): ChartColors {
  const styles =
    typeof window === "undefined" ? null : window.getComputedStyle(document.documentElement);
  return {
    surface: token(styles, "--color-panel"),
    ink: token(styles, "--color-ink"),
    inkMuted: token(styles, "--color-ink-muted"),
    grid: token(styles, "--color-grid"),
    axis: token(styles, "--color-axis"),
    up: token(styles, "--color-up"),
    down: token(styles, "--color-down"),
    indicatorLines: INDICATOR_LINE_TOKENS.map((name) => token(styles, name)),
    drawingLines: DRAWING_LINE_TOKENS.map((name) => token(styles, name)),
  };
}

/**
 * Up candles are drawn hollow, down candles filled. That is the **secondary
 * encoding** the palette validator demands: teal-vs-red clears every gate
 * except a protan CVD warning (ΔE 6.5, inside the 6–8 floor band), which is
 * only legal when something other than hue also carries the distinction. Body
 * fill does — it survives any color vision, and greyscale printing too.
 */
export function candlestickColors(colors: ChartColors) {
  return {
    upColor: colors.surface,
    downColor: colors.down,
    borderVisible: true,
    borderUpColor: colors.up,
    borderDownColor: colors.down,
    wickUpColor: colors.up,
    wickDownColor: colors.down,
  };
}

export function indicatorLineColor(colors: ChartColors, index: number): string {
  return colors.indicatorLines[index % colors.indicatorLines.length];
}

/**
 * The colour a token names, in whatever theme is current — `indicatorLines` is built from
 * the same list in the same order, so the token's position in it is the lookup. Null for
 * anything that is not one of the eight: a saved slot may name a token this palette no
 * longer has, and that must read as "assign one" rather than paint the line undefined.
 */
export function indicatorColorFromToken(colors: ChartColors, token: string | null): string | null {
  if (token === null) return null;
  const index = INDICATOR_LINE_TOKENS.indexOf(token as IndicatorColorToken);
  return index === -1 ? null : colors.indicatorLines[index];
}

/**
 * A drawing's colour from whatever token it was saved with — its own palette first, and
 * the indicator one after it.
 *
 * The second half is not a courtesy: drawings were put on instruments before the drawing
 * palette existed, and every one of them carries an indicator token. The tool stopped
 * offering those (`agent/tools/drawings.py`), so nothing new arrives in one; forgetting
 * the old ones here would blank objects the operator never touched (design.md, "Paleta
 * rysunków dokłada tokeny, nie odbiera starych").
 */
export function drawingColorFromToken(colors: ChartColors, token: string | null): string | null {
  if (token === null) return null;
  const index = DRAWING_LINE_TOKENS.indexOf(token as DrawingColorToken);
  if (index !== -1) return colors.drawingLines[index];
  return indicatorColorFromToken(colors, token);
}

/**
 * The colour the chart gives a drawing that named none — a function of the drawing's own
 * id, so it is the same in every slot, after every reload, and after the object beside it
 * is deleted (`terminal-chart` spec, "Kolor obiektu po usunięciu innego"). The old
 * position-in-the-list cycle repainted every drawing after the one removed.
 *
 * Ids are consecutive, so objects drawn in one sitting land on different hues, which is
 * the case that matters. Two objects far apart in id can share one; with a hundred
 * objects allowed on an instrument that is unavoidable for any finite palette, and the
 * alternative — handing out the next free colour — is a state that depends on the
 * neighbours again (design.md, "Kolor przypisywany po identyfikatorze, nie po pozycji").
 */
export function drawingColorFor(id: number, colors: ChartColors): string {
  const palette = colors.drawingLines;
  return palette[Math.abs(Math.trunc(id)) % palette.length];
}
