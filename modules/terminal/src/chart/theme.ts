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
  "--color-panel": "#1a1a19",
  "--color-ink": "#ffffff",
  "--color-ink-muted": "#898781",
  "--color-grid": "#2c2c2a",
  "--color-axis": "#383835",
  "--color-up": "#199e70",
  "--color-down": "#e66767",
  "--color-accent": "#3987e5",
  "--color-indicator-2": "#d95926",
  "--color-indicator-4": "#c98500",
  "--color-indicator-5": "#d55181",
  "--color-indicator-6": "#008300",
  "--color-indicator-7": "#9085e9",
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
const INDICATOR_LINE_TOKENS = [
  "--color-accent",
  "--color-indicator-2",
  "--color-up",
  "--color-indicator-4",
  "--color-indicator-5",
  "--color-indicator-6",
  "--color-indicator-7",
  "--color-down",
] as const;

export interface ChartColors {
  surface: string;
  ink: string;
  inkMuted: string;
  grid: string;
  axis: string;
  up: string;
  down: string;
  /** Fixed order, indexed by how many wskaźnik lines are already drawn — never by
   *  which one a line is, so adding or removing one never repaints another
   *  (dataviz skill, "Color follows the entity, never its rank"; here the order of
   *  appearance is the entity, since a line has no identity a legend names). Cycles
   *  past the eighth concurrent line rather than inventing a ninth hue. */
  indicatorLines: readonly string[];
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
