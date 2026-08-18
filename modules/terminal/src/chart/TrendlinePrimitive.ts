import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  PrimitiveHoveredItem,
  Time,
} from "lightweight-charts";

import {
  HIT_TOLERANCE,
  distanceToSegment,
  drawChip,
  strokeSpec,
  type Emphasis,
  type MarkOptions,
  type MarkPalette,
  type MarkWeight,
} from "./drawingStyle";
import { MarkPrimitive } from "./MarkPrimitive";
import { timeToX } from "./timeCoordinates";

/**
 * A line between two time–price points — the one shape neither `RayPrimitive` nor
 * `ZonePrimitive` already draws, and the reason this file exists
 * (`terminal-chart` spec, "Linia trendu MUST być odcinkiem między swoimi punktami").
 *
 * Built on `RayPrimitive`'s frame — same class shape, same `timeToX` — with one
 * difference that is the whole point: a ray runs to the right edge and this stops where
 * it was told to. It is **not** extended past its points and **not** clipped to the
 * visible range: a segment drawn only as far as the screen reaches would change slope
 * with the pan, and an extended one would claim a level the operator never drew. The
 * canvas clips what falls outside the pane on its own, which is the correct clipping and
 * costs nothing here.
 */
export interface DrawnTrendline {
  from: Time;
  to: Time;
  fromPrice: number;
  toPrice: number;
  label: string | null;
  /** Null falls back to the primitive's own colour — the chart's choice for a drawing
   *  that named none. */
  color: string | null;
}

interface TrendlineRenderItem {
  x1: number | null;
  y1: number | null;
  x2: number | null;
  y2: number | null;
  color: string;
  label: string | null;
}

class TrendlinePaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly TrendlineRenderItem[];
  private readonly weight: MarkWeight;
  private readonly emphasis: Emphasis;
  private readonly palette: MarkPalette;

  constructor(source: TrendlinePrimitive) {
    this.items = source.renderItems();
    this.weight = source.markWeight;
    this.emphasis = source.emphasis;
    this.palette = source.palette;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const stroke = strokeSpec(this.weight, this.emphasis);
      for (const item of this.items) {
        // Either endpoint unplaceable means there is no segment to draw — unlike a ray,
        // whose far end is the pane's edge and always exists. Both coordinates are kept
        // whatever they are, negative ones included: clamping the left end to 0 the way
        // `RayPrimitive` does would tilt a line whose start is off-screen.
        if (item.x1 === null || item.y1 === null || item.x2 === null || item.y2 === null) continue;
        const x1 = item.x1 * scope.horizontalPixelRatio;
        const x2 = item.x2 * scope.horizontalPixelRatio;
        const y1 = item.y1 * scope.verticalPixelRatio;
        const y2 = item.y2 * scope.verticalPixelRatio;

        ctx.save();
        ctx.strokeStyle = item.color;
        if (stroke.halo > 0) {
          ctx.globalAlpha = 0.3;
          ctx.lineWidth = stroke.halo * scope.verticalPixelRatio;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        }
        ctx.globalAlpha = stroke.alpha;
        ctx.lineWidth = stroke.lineWidth * scope.verticalPixelRatio;
        ctx.setLineDash(stroke.dash);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        if (item.label) {
          // At the later end, where a trend line is read from: the newest point is the
          // one the operator is looking at when the chart sits at the live edge. The chip
          // keeps itself inside the pane from there, so a line running in from off-screen
          // is still named.
          drawChip(ctx, item.label, item.color, this.palette, {
            x: x2,
            y: y2,
            ratio: scope.verticalPixelRatio,
            paneWidth: scope.bitmapSize.width,
          });
        }
        ctx.restore();
      }
    });
  }
}

class TrendlinePaneView implements IPrimitivePaneView {
  private readonly source: TrendlinePrimitive;

  constructor(source: TrendlinePrimitive) {
    this.source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new TrendlinePaneRenderer(this.source);
  }
}

export class TrendlinePrimitive extends MarkPrimitive<TrendlineRenderItem> {
  private lines: readonly DrawnTrendline[] = [];
  private color: string;
  protected readonly views: readonly IPrimitivePaneView[] = [new TrendlinePaneView(this)];

  constructor(color: string, options: MarkOptions = {}) {
    super(options);
    this.color = color;
  }

  setLines(lines: readonly DrawnTrendline[]): void {
    this.lines = lines;
    this.rebuildAxisViews();
  }

  setColor(color: string): void {
    this.color = color;
  }

  /** The tolerance band around the segment itself, not around the whole line it lies on:
   *  a trend line ends where it was drawn to end, and so does the click into it. */
  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const id = this.objectId;
    if (id === null) return null;
    for (const item of this.renderItems()) {
      if (item.x1 === null || item.y1 === null || item.x2 === null || item.y2 === null) continue;
      if (distanceToSegment(x, y, item.x1, item.y1, item.x2, item.y2) > HIT_TOLERANCE) continue;
      return { externalId: id, zOrder: "normal", cursorStyle: "pointer" };
    }
    return null;
  }

  renderItems(): TrendlineRenderItem[] {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return [];
    const timeScale = chart.timeScale();
    // No visible-range filter, unlike `ZonePrimitive`: a trend line crossing the screen
    // with both of its ends outside it is exactly the case that must still draw, and the
    // handful of drawings an instrument carries never makes the filter worth its risk.
    return this.lines.map((line) => ({
      x1: timeToX(timeScale, line.from),
      y1: series.priceToCoordinate(line.fromPrice),
      x2: timeToX(timeScale, line.to),
      y2: series.priceToCoordinate(line.toPrice),
      color: line.color ?? this.color,
      label: line.label,
    }));
  }

  /** Both ends, the same two prices the object list shows for a trend line. */
  protected axisEntries() {
    return this.lines.flatMap((line) =>
      [line.fromPrice, line.toPrice].map((price) => ({
        price,
        color: () => line.color ?? this.color,
      })),
    );
  }
}
