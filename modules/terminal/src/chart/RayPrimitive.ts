import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  PrimitiveHoveredItem,
  Time,
} from "lightweight-charts";

import {
  HIT_TOLERANCE,
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
 * One `levels`-shaped price ray: a segment from the moment it took effect to the right edge — never the
 * whole width, unlike `createPriceLine`.
 */
export interface RayLevel {
  time: Time;
  price: number;
  label: string | null;
}

interface RayRenderItem {
  x: number | null;
  y: number | null;
  color: string;
  label: string | null;
}

class RayPaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly RayRenderItem[];
  private readonly weight: MarkWeight;
  private readonly emphasis: Emphasis;
  private readonly palette: MarkPalette;

  constructor(source: RayPrimitive) {
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
        if (item.x === null || item.y === null) continue;
        const xStart = Math.max(0, item.x) * scope.horizontalPixelRatio;
        const xEnd = scope.bitmapSize.width;
        const y = Math.round(item.y * scope.verticalPixelRatio) + 0.5;

        ctx.save();
        ctx.globalAlpha = stroke.alpha;
        ctx.strokeStyle = item.color;
        if (stroke.halo > 0) {
          // Under the line and wider than it, in the line's own colour: the picked
          // object reads as picked without its position or its hue changing.
          ctx.globalAlpha = 0.3;
          ctx.lineWidth = stroke.halo * scope.verticalPixelRatio;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(xStart, y);
          ctx.lineTo(xEnd, y);
          ctx.stroke();
          ctx.globalAlpha = stroke.alpha;
        }
        ctx.lineWidth = stroke.lineWidth * scope.verticalPixelRatio;
        ctx.setLineDash(stroke.dash);
        ctx.beginPath();
        ctx.moveTo(xStart, y);
        ctx.lineTo(xEnd, y);
        ctx.stroke();

        if (item.label) {
          drawChip(ctx, item.label, item.color, this.palette, {
            x: xStart,
            y,
            ratio: scope.verticalPixelRatio,
            paneWidth: scope.bitmapSize.width,
          });
        }
        ctx.restore();
      }
    });
  }
}

class RayPaneView implements IPrimitivePaneView {
  private readonly source: RayPrimitive;

  constructor(source: RayPrimitive) {
    this.source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new RayPaneRenderer(this.source);
  }
}

/**
 * Every `IndicatorLevel` a `levels` entry answered with, replaced wholesale on every recompute; the same class
 * draws an operator's own level at the `drawing` weight. Coordinates are read fresh — the list is short.
 */
export class RayPrimitive extends MarkPrimitive<RayRenderItem> {
  private levels: readonly RayLevel[] = [];
  private color: string;
  protected readonly views: readonly IPrimitivePaneView[] = [new RayPaneView(this)];

  constructor(color: string, options: MarkOptions = {}) {
    super(options);
    this.color = color;
  }

  setLevels(levels: readonly RayLevel[]): void {
    this.levels = levels;
    this.rebuildAxisViews();
  }

  setColor(color: string): void {
    this.color = color;
  }

  /**
   * A band around the ray, from the moment it starts to the right edge.
   */
  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const id = this.objectId;
    if (id === null) return null;
    for (const item of this.renderItems()) {
      if (item.x === null || item.y === null) continue;
      if (x < Math.max(0, item.x) - HIT_TOLERANCE) continue;
      if (Math.abs(y - item.y) > HIT_TOLERANCE) continue;
      return { externalId: id, zOrder: "normal", cursorStyle: "pointer" };
    }
    return null;
  }

  renderItems(): RayRenderItem[] {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return [];
    const timeScale = chart.timeScale();
    return this.levels.map((level) => ({
      // `null` only when the chart holds no bars at all. A moment inside the loaded range that is not
      // itself a bar snaps to the nearest one rather than dropping the ray.
      x: timeToX(timeScale, level.time),
      y: series.priceToCoordinate(level.price),
      color: this.color,
      label: level.label,
    }));
  }

  protected axisEntries() {
    return this.levels.map((level) => ({ price: level.price, color: () => this.color }));
  }
}
