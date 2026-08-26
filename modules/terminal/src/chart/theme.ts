/**
 * The chart is a canvas and cannot wear a Tailwind class, so it reads `index.css`'s `@theme` tokens as plain
 * strings. Fallbacks exist because jsdom has no stylesheet, and empty colours throw deep inside the library.
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
 * This codebase's whole validated categorical palette, in the documented order and at the positions the
 * validator's adjacent-pair check requires. Any other subset or order failed that check.
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
 * The objects an operator draws, in four hues none of the eight above uses — an object that cannot be told
 * from an indicator line is why this list exists. Four is where the validator's all-pairs list still clears.
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
  /** Fixed order, indexed by how many indicator lines are already drawn — never by which one a line is,
   *  so adding or removing one never repaints another. Cycles past the eighth rather than inventing a hue. */
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
 * Up candles hollow, down filled — the secondary encoding the palette validator demands: teal-vs-red clears
 * every gate but a protan warning, legal only when something other than hue carries the distinction.
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
 * The colour a token names, in whatever theme is current. Null for anything that is not one of the eight:
 * a saved slot may name a token this palette no longer has, and that must read as "assign one".
 */
export function indicatorColorFromToken(colors: ChartColors, token: string | null): string | null {
  if (token === null) return null;
  const index = INDICATOR_LINE_TOKENS.indexOf(token as IndicatorColorToken);
  return index === -1 ? null : colors.indicatorLines[index];
}

/**
 * A drawing's colour from whatever token it was saved with — its own palette first, the indicator one after.
 * The second half is not a courtesy: objects predate the drawing palette, and would blank without it.
 */
export function drawingColorFromToken(colors: ChartColors, token: string | null): string | null {
  if (token === null) return null;
  const index = DRAWING_LINE_TOKENS.indexOf(token as DrawingColorToken);
  if (index !== -1) return colors.drawingLines[index];
  return indicatorColorFromToken(colors, token);
}

/**
 * A function of the drawing's own id, so it is the same in every slot and after the object beside it is
 * deleted — the old position-in-the-list cycle repainted everything after the one removed.
 */
export function drawingColorFor(id: number, colors: ChartColors): string {
  const palette = colors.drawingLines;
  return palette[Math.abs(Math.trunc(id)) % palette.length];
}
