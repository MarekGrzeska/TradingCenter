import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitiveAxisView,
  PrimitiveHoveredItem,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

import {
  DrawingPriceAxisView,
  HIT_TOLERANCE,
  defaultMarkPalette,
  drawChip,
  strokeSpec,
  type Emphasis,
  type MarkOptions,
  type MarkPalette,
  type MarkWeight,
} from "./drawingStyle";
import { timeToX } from "./timeCoordinates";

/**
 * One `levels`-shaped price ray: a segment from the moment it took effect to the
 * right edge — never the whole width, unlike `createPriceLine` (`terminal-chart`
 * spec, "Strefy i poziomy rysują się jako obszary, nie jako linie serii"; plan
 * doc, "PDH ma się zaczynać w konkretnym momencie").
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
 * A series primitive drawing every `IndicatorLevel` a `levels`-output indicator
 * answered with — one instance per (id, params) result, its `levels` replaced
 * wholesale on every recompute rather than diffed, the same way a Line series'
 * `setData` replaces its points (task 3.9). The same class also draws an operator's
 * own level, told apart by the `drawing` weight it is built with.
 *
 * Coordinates are read fresh on every `renderer()` call rather than cached: the
 * library asks for one on every repaint, panning and zooming included, and the
 * levels list this holds is short enough (a handful of pivots or PDH/PDL rays)
 * that recomputing costs nothing worth caching against.
 */
export class RayPrimitive implements ISeriesPrimitive<Time> {
  private levels: readonly RayLevel[] = [];
  private color: string;
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType, Time> | null = null;
  private currentPrice: number | null = null;
  private requestUpdate: (() => void) | null = null;
  private axisViews: readonly ISeriesPrimitiveAxisView[] = [];
  private readonly views: readonly IPrimitivePaneView[] = [new RayPaneView(this)];

  readonly markWeight: MarkWeight;
  readonly objectId: string | null;
  readonly palette: MarkPalette;
  emphasis: Emphasis = "normal";

  constructor(color: string, options: MarkOptions = {}) {
    this.color = color;
    this.markWeight = options.weight ?? "indicator";
    this.objectId = options.objectId ?? null;
    this.palette = options.palette ?? defaultMarkPalette();
  }

  setLevels(levels: readonly RayLevel[]): void {
    this.levels = levels;
    this.rebuildAxisViews();
  }

  setColor(color: string): void {
    this.color = color;
  }

  /** The newest close, for the axis label's role. Null while the chart has drawn no
   *  candle — see `roleColor`. */
  setCurrentPrice(price: number | null): void {
    this.currentPrice = price;
  }

  setEmphasis(emphasis: Emphasis): void {
    if (this.emphasis === emphasis) return;
    this.emphasis = emphasis;
    this.requestUpdate?.();
  }

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>): void {
    this.chart = chart;
    this.series = series;
    this.requestUpdate = requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Only an operator's object announces its price at the axis. Every level a `levels`
   *  indicator answers with would announce one too, and a chart with `level_clusters` on
   *  it would have an axis of nothing else. */
  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return this.axisViews;
  }

  /**
   * A band around the ray, from the moment it starts to the right edge. Null for an
   * indicator's own primitive: what a click picks out is an object somebody drew, not a
   * reading (`terminal-chart-objects` spec, "Operator wskazuje obiekt na wykresie").
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

  /** Package-visible for `RayPaneView`, not the public API of this class. */
  renderItems(): RayRenderItem[] {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return [];
    const timeScale = chart.timeScale();
    return this.levels.map((level) => ({
      // `null` only when the chart holds no bars at all. A moment inside the
      // loaded range that is not itself a bar — a previous-day close at a
      // midnight the venue was shut through — snaps to the nearest one rather
      // than dropping the ray (`timeCoordinates.ts`).
      x: timeToX(timeScale, level.time),
      y: series.priceToCoordinate(level.price),
      color: this.color,
      label: level.label,
    }));
  }

  /** A fresh array only when the set of labels changed — the library caches these by
   *  reference and rebuilding one per repaint would defeat that. */
  private rebuildAxisViews(): void {
    if (this.objectId === null) {
      this.axisViews = [];
      return;
    }
    this.axisViews = this.levels.map(
      (level) =>
        new DrawingPriceAxisView(() => ({
          coordinate: this.series?.priceToCoordinate(level.price) ?? null,
          price: level.price,
          color: this.color,
          currentPrice: this.currentPrice,
          palette: this.palette,
        })),
    );
  }
}
