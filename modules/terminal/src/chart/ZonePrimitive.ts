import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  PrimitiveHoveredItem,
  Time,
} from "lightweight-charts";

import {
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
 * One `zones`-shaped region: a rectangle from the moment it took effect to the moment it closed, open to
 * the right edge while `to` is null.
 */
export interface DrawnZone {
  from: Time;
  to: Time | null;
  top: number;
  bottom: number;
  direction: "bullish" | "bearish" | null;
  /** Only an operator's band carries one; an indicator's zones are named by the
   *  indicator, not one by one. */
  label?: string | null;
}

export interface ZoneColors {
  bullish: string;
  bearish: string;
  neutral: string;
}

interface ZoneRenderItem {
  xStart: number | null;
  /** Open to the right: the rectangle reaches the pane's own right edge, never the whole chart width.
   *  Kept apart from a null `xEnd`, which means the end moment resolved to no coordinate — the two used
   *  to be one `null`, so an unplaceable end silently became an open zone. */
  open: boolean;
  xEnd: number | null;
  yTop: number | null;
  yBottom: number | null;
  color: string;
  label: string | null;
}

const FILL_ALPHA = 0.18;

class ZonePaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly ZoneRenderItem[];
  private readonly weight: MarkWeight;
  private readonly emphasis: Emphasis;
  private readonly palette: MarkPalette;

  constructor(source: ZonePrimitive) {
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
        if (item.xStart === null || item.yTop === null || item.yBottom === null) continue;
        if (!item.open && item.xEnd === null) continue;
        const xStart = Math.max(0, item.xStart) * scope.horizontalPixelRatio;
        const xEnd =
          item.open || item.xEnd === null
            ? scope.bitmapSize.width
            : item.xEnd * scope.horizontalPixelRatio;
        const yTop = Math.min(item.yTop, item.yBottom) * scope.verticalPixelRatio;
        const yBottom = Math.max(item.yTop, item.yBottom) * scope.verticalPixelRatio;

        ctx.save();
        ctx.globalAlpha = FILL_ALPHA * stroke.alpha;
        ctx.fillStyle = item.color;
        ctx.fillRect(xStart, yTop, Math.max(xEnd - xStart, 0), Math.max(yBottom - yTop, 1));
        ctx.restore();

        // A band the operator drew gets its edges outlined at the drawing's own weight; a computed one
        // stays the bare wash it always was.
        if (this.weight === "drawing") {
          ctx.save();
          ctx.strokeStyle = item.color;
          if (stroke.halo > 0) {
            // Outside the band's own edge and wider than it, the same wash the other two
            // shapes wear when they are the one picked out.
            ctx.globalAlpha = 0.3;
            ctx.lineWidth = stroke.halo * scope.verticalPixelRatio;
            ctx.setLineDash([]);
            ctx.strokeRect(xStart, yTop, Math.max(xEnd - xStart, 0), Math.max(yBottom - yTop, 1));
          }
          ctx.globalAlpha = stroke.alpha;
          ctx.lineWidth = stroke.lineWidth * scope.verticalPixelRatio;
          ctx.setLineDash(stroke.dash);
          ctx.strokeRect(xStart, yTop, Math.max(xEnd - xStart, 0), Math.max(yBottom - yTop, 1));
          if (item.label) {
            drawChip(ctx, item.label, item.color, this.palette, {
              x: xStart,
              y: yTop,
              ratio: scope.verticalPixelRatio,
              paneWidth: scope.bitmapSize.width,
            });
          }
          ctx.restore();
        }
      }
    });
  }
}

class ZonePaneView implements IPrimitivePaneView {
  private readonly source: ZonePrimitive;

  constructor(source: ZonePrimitive) {
    this.source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new ZonePaneRenderer(this.source);
  }
}

function colorFor(direction: DrawnZone["direction"], colors: ZoneColors): string {
  if (direction === "bullish") return colors.bullish;
  if (direction === "bearish") return colors.bearish;
  return colors.neutral;
}

/**
 * Every `Zone` a `zones` entry answered with, and an operator's own band at the `drawing` weight. Only zones
 * overlapping the visible range are mapped to screen coordinates: a few hundred open would cost that per repaint.
 */
export class ZonePrimitive extends MarkPrimitive<ZoneRenderItem> {
  private zones: readonly DrawnZone[] = [];
  private colors: ZoneColors;
  protected readonly views: readonly IPrimitivePaneView[] = [new ZonePaneView(this)];

  constructor(colors: ZoneColors, options: MarkOptions = {}) {
    super(options);
    this.colors = colors;
  }

  setZones(zones: readonly DrawnZone[]): void {
    this.zones = zones;
    this.rebuildAxisViews();
  }

  setColors(colors: ZoneColors): void {
    this.colors = colors;
  }

  /** The band's own rectangle is the tolerance — a shape with an area needs no margin
   *  around it the way a line does. */
  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const id = this.objectId;
    if (id === null) return null;
    for (const item of this.renderItems()) {
      if (item.xStart === null || item.yTop === null || item.yBottom === null) continue;
      if (!item.open && item.xEnd === null) continue;
      // An open band runs to whatever the right edge is at this moment, which the pane
      // knows and this does not — unbounded is the same answer without asking.
      const right = item.open || item.xEnd === null ? Number.POSITIVE_INFINITY : item.xEnd;
      if (x < Math.max(0, item.xStart) || x > right) continue;
      if (y < Math.min(item.yTop, item.yBottom) || y > Math.max(item.yTop, item.yBottom)) continue;
      return { externalId: id, zOrder: "normal", cursorStyle: "pointer" };
    }
    return null;
  }

  renderItems(): ZoneRenderItem[] {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return [];
    const timeScale = chart.timeScale();
    const visible = timeScale.getVisibleRange();
    if (!visible) return [];

    const items: ZoneRenderItem[] = [];
    for (const zone of this.zones) {
      // A zone entirely before or after the visible window contributes
      // nothing on screen — skipped before any coordinate is resolved.
      if (zone.to !== null && (zone.to as number) < (visible.from as number)) continue;
      if ((zone.from as number) > (visible.to as number)) continue;

      items.push({
        open: zone.to === null,
        xStart: timeToX(timeScale, zone.from),
        xEnd: zone.to === null ? null : timeToX(timeScale, zone.to),
        yTop: series.priceToCoordinate(zone.top),
        yBottom: series.priceToCoordinate(zone.bottom),
        color: colorFor(zone.direction, this.colors),
        label: zone.label ?? null,
      });
    }
    return items;
  }

  /** Both edges, the same two prices the object list shows for a zone. */
  protected axisEntries() {
    return this.zones.flatMap((zone) =>
      [zone.top, zone.bottom].map((price) => ({
        price,
        color: () => colorFor(zone.direction, this.colors),
      })),
    );
  }
}
