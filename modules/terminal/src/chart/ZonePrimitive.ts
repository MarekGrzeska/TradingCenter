import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

/**
 * One `zones`-shaped region: a rectangle from the moment it took effect to
 * the moment it closed, open to the right edge while `to` is null — the same
 * null `IndicatorZoneOut.to` already carries (`terminal-chart` spec, "Strefy
 * i poziomy rysują się jako obszary, nie jako linie serii"; task 4.6).
 */
export interface DrawnZone {
  from: Time;
  to: Time | null;
  top: number;
  bottom: number;
  direction: "bullish" | "bearish" | null;
}

export interface ZoneColors {
  bullish: string;
  bearish: string;
  neutral: string;
}

interface ZoneRenderItem {
  xStart: number | null;
  /** `null` means open — the rectangle reaches the pane's own right edge,
   *  never the whole chart width, the same distinction `RayPrimitive` draws
   *  for a ray's right end. */
  xEnd: number | null;
  yTop: number | null;
  yBottom: number | null;
  color: string;
}

const FILL_ALPHA = 0.18;

class ZonePaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly ZoneRenderItem[];

  constructor(items: readonly ZoneRenderItem[]) {
    this.items = items;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      for (const item of this.items) {
        if (item.xStart === null || item.yTop === null || item.yBottom === null) continue;
        const xStart = Math.max(0, item.xStart) * scope.horizontalPixelRatio;
        const xEnd =
          item.xEnd === null ? scope.bitmapSize.width : item.xEnd * scope.horizontalPixelRatio;
        const yTop = Math.min(item.yTop, item.yBottom) * scope.verticalPixelRatio;
        const yBottom = Math.max(item.yTop, item.yBottom) * scope.verticalPixelRatio;

        ctx.save();
        ctx.globalAlpha = FILL_ALPHA;
        ctx.fillStyle = item.color;
        ctx.fillRect(xStart, yTop, Math.max(xEnd - xStart, 0), Math.max(yBottom - yTop, 1));
        ctx.restore();
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
    return new ZonePaneRenderer(this.source.renderItems());
  }
}

function colorFor(direction: DrawnZone["direction"], colors: ZoneColors): string {
  if (direction === "bullish") return colors.bullish;
  if (direction === "bearish") return colors.bearish;
  return colors.neutral;
}

/**
 * A series primitive drawing every `Zone` a `zones`-output indicator answered
 * with — `range_gap`, `body_gap`, `session_range_*`, `opening_range` (task
 * 4.7). Its zones are replaced wholesale on every recompute, the same
 * convention `RayPrimitive.setLevels` already uses for `levels`.
 *
 * Only zones overlapping the time scale's current visible range are turned
 * into screen coordinates at all — with a few hundred zones open on a wide
 * chart (task 4.10's ~300), mapping every one of them on every repaint (pan,
 * zoom, a live tick) is the cost `renderItems()`'s own filter exists to
 * avoid, before a single `timeToCoordinate` call is spent on one that is not
 * on screen.
 */
export class ZonePrimitive implements ISeriesPrimitive<Time> {
  private zones: readonly DrawnZone[] = [];
  private colors: ZoneColors;
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType, Time> | null = null;
  private readonly views: readonly IPrimitivePaneView[] = [new ZonePaneView(this)];

  constructor(colors: ZoneColors) {
    this.colors = colors;
  }

  setZones(zones: readonly DrawnZone[]): void {
    this.zones = zones;
  }

  setColors(colors: ZoneColors): void {
    this.colors = colors;
  }

  attached({ chart, series }: SeriesAttachedParameter<Time>): void {
    this.chart = chart;
    this.series = series;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Package-visible for `ZonePaneView`, not the public API of this class. */
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
        xStart: timeScale.timeToCoordinate(zone.from),
        xEnd: zone.to === null ? null : timeScale.timeToCoordinate(zone.to),
        yTop: series.priceToCoordinate(zone.top),
        yBottom: series.priceToCoordinate(zone.bottom),
        color: colorFor(zone.direction, this.colors),
      });
    }
    return items;
  }
}
