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
};

function token(styles: CSSStyleDeclaration | null, name: string): string {
  const value = styles?.getPropertyValue(name).trim();
  return value || FALLBACKS[name];
}

export interface ChartColors {
  surface: string;
  ink: string;
  inkMuted: string;
  grid: string;
  axis: string;
  up: string;
  down: string;
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
