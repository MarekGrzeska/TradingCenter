/**
 * What separates an object the operator drew from a line the catalogue computed, and the
 * geometry a click into one has to satisfy.
 *
 * It lives here rather than three times over because the three primitives draw three
 * shapes with one vocabulary: weight says who made the mark, the chip carries its caption
 * over the candles, the axis label says where it sits, and the tolerance band says how
 * near a click has to land. Three copies of that would drift, and the drift shows up as
 * "sometimes the level cannot be clicked" (design.md, "Trafianie natywnym `hitTest`").
 */

import type { ISeriesPrimitiveAxisView } from "lightweight-charts";
import { readChartColors } from "./theme";

/**
 * Who put the mark on the chart. 2 px solid is an operator's ruling, 1 px dashed a
 * reading taken from the archive — the difference is carried by weight rather than by
 * colour alone, because a chart with eight hues on it gives nobody a way to remember
 * which four belong to which group (design.md, "Rysunek cięższy od wskaźnika").
 */
export type MarkWeight = "drawing" | "indicator";

/** How the object stands relative to whatever the operator has picked out: the one
 *  picked, one of the rest while something is picked, or nothing picked at all. */
export type Emphasis = "normal" | "selected" | "dimmed";

/** The three theme colours a mark needs beyond its own: what text on a filled plate is
 *  drawn in, and the two the price-axis label uses to say which side of the price the
 *  object sits on. Same tokens as the rising and falling candle — "below the price" and
 *  "above the price" is exactly the meaning those two already carry here. */
export interface MarkPalette {
  onFill: string;
  support: string;
  resistance: string;
}

export function defaultMarkPalette(): MarkPalette {
  const colors = readChartColors();
  return { onFill: colors.surface, support: colors.up, resistance: colors.down };
}

export interface MarkOptions {
  weight?: MarkWeight;
  /** The drawing's own id as text. Non-null is what makes the primitive clickable and
   *  what a click reports back; an indicator primitive leaves it null and is never hit
   *  (`terminal-chart-objects` spec — the selectable objects are drawings, not readings). */
  objectId?: string | null;
  palette?: MarkPalette;
}

/** How near a click has to land. A line is a couple of pixels wide and a pointer is not
 *  precise to the pixel, so a click beside it is a click into it (`terminal-chart-objects`
 *  spec, "Kliknięcie obok linii, w granicach tolerancji"). */
export const HIT_TOLERANCE = 5;

const CHIP_FONT_PX = 10;
const CHIP_PAD_X = 4;
const CHIP_PAD_Y = 2;
/** Between the chip's lower edge and the line it belongs to. */
const CHIP_GAP = 3;

export interface StrokeSpec {
  lineWidth: number;
  dash: number[];
  alpha: number;
  /** Width of the wash drawn under the line for the picked object, or 0 for none — what
   *  makes "picked" visible without moving the line itself. */
  halo: number;
}

export function strokeSpec(weight: MarkWeight, emphasis: Emphasis): StrokeSpec {
  const base = weight === "drawing" ? 2 : 1;
  const dash = weight === "drawing" ? [] : [4, 4];
  if (emphasis === "selected") return { lineWidth: base + 1, dash, alpha: 1, halo: base + 6 };
  if (emphasis === "dimmed") return { lineWidth: base, dash, alpha: 0.35, halo: 0 };
  return { lineWidth: base, dash, alpha: 1, halo: 0 };
}

/** The subset of a canvas context the chip needs, so a test can hand over a recorder
 *  rather than a canvas — the same boundary the primitives' own tests already draw. */
export interface ChipContext {
  fillRect(x: number, y: number, width: number, height: number): void;
  fillText(text: string, x: number, y: number): void;
  measureText(text: string): { width: number };
  /** As wide as the real context's own, so a `CanvasRenderingContext2D` satisfies this
   *  without a cast at every call site — the chip only ever assigns a string to it. */
  fillStyle: string | CanvasGradient | CanvasPattern;
  font: string;
  textBaseline: CanvasTextBaseline;
}

export interface ChipPlacement {
  /** Left edge of the plate, in bitmap pixels. */
  x: number;
  /** The line the caption belongs to; the plate sits above it. */
  y: number;
  ratio: number;
  /** Pane width in bitmap pixels — the plate is kept inside it, so an object whose start
   *  is off to the left is still named (`terminal-chart` spec, "Obiekt zaczynający się
   *  poza widokiem"). */
  paneWidth: number;
}

/**
 * The caption on a filled plate rather than as bare text. Text laid straight on the chart
 * disappears into the wicks; the plate is what makes it readable over them
 * (`terminal-chart` spec, "Etykieta MUST być czytelna nad świecami").
 */
export function drawChip(
  ctx: ChipContext,
  text: string,
  color: string,
  palette: MarkPalette,
  { x, y, ratio, paneWidth }: ChipPlacement,
): void {
  const font = `${CHIP_FONT_PX * ratio}px sans-serif`;
  ctx.font = font;
  const width = ctx.measureText(text).width + 2 * CHIP_PAD_X * ratio;
  const height = CHIP_FONT_PX * ratio + 2 * CHIP_PAD_Y * ratio;
  // Clamped at both ends: past the right edge the plate would be cut in half, before the
  // left one it would not be there at all.
  const left = Math.min(Math.max(x, 0), Math.max(paneWidth - width, 0));
  const top = y - CHIP_GAP * ratio - height;

  ctx.fillStyle = color;
  ctx.fillRect(left, top, width, height);
  ctx.fillStyle = palette.onFill;
  ctx.textBaseline = "middle";
  ctx.fillText(text, left + CHIP_PAD_X * ratio, top + height / 2);
}

/**
 * The colour of the object's label at the price axis — its role, not its own colour.
 *
 * The line already says *which* object this is; the axis label is the one place left to
 * say *what* it is, and that costs nothing since the label is drawn either way
 * (design.md, "Kolor: linia z palety rysunków, etykieta przy osi kolorowana rolą"). The
 * role is recomputed from the newest candle, so a level the price breaks through stops
 * calling itself resistance on its own — which is the point.
 */
export function roleColor(
  price: number,
  currentPrice: number | null,
  lineColor: string,
  palette: MarkPalette,
): string {
  // A chart with no candle drawn yet has nothing for the object to sit above or below;
  // guessing a side there would be a claim, so the line's own colour stands in.
  if (currentPrice === null) return lineColor;
  return price <= currentPrice ? palette.support : palette.resistance;
}

/** One price of one drawn object, at the axis. Reads the primitive live on every call —
 *  the library asks on each repaint, and a coordinate cached here would be the panned-away
 *  one. */
export class DrawingPriceAxisView implements ISeriesPrimitiveAxisView {
  private readonly read: () => {
    coordinate: number | null;
    price: number;
    color: string;
    currentPrice: number | null;
    palette: MarkPalette;
  };

  constructor(read: DrawingPriceAxisView["read"]) {
    this.read = read;
  }

  coordinate(): number {
    // Off-screen rather than at the top: a label for a price the series cannot place must
    // not land on a coordinate that means something else.
    return this.read().coordinate ?? -1000;
  }

  text(): string {
    return String(this.read().price);
  }

  textColor(): string {
    return this.read().palette.onFill;
  }

  backColor(): string {
    const { price, currentPrice, color, palette } = this.read();
    return roleColor(price, currentPrice, color, palette);
  }

  visible(): boolean {
    return this.read().coordinate !== null;
  }
}

/** Distance from a point to a segment, for the tolerance band a click has to fall in.
 *  A degenerate segment (both ends at one point) falls out as the distance to that
 *  point, which is what the arithmetic gives without a branch of its own. */
export function distanceToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;
  const t =
    lengthSquared === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  const nearestX = x1 + t * dx;
  const nearestY = y1 + t * dy;
  return Math.hypot(px - nearestX, py - nearestY);
}
