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

const LABEL_FONT = "10px sans-serif";
const LABEL_PADDING = 4;

class RayPaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly RayRenderItem[];

  constructor(items: readonly RayRenderItem[]) {
    this.items = items;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      for (const item of this.items) {
        if (item.x === null || item.y === null) continue;
        const xStart = Math.max(0, item.x) * scope.horizontalPixelRatio;
        const xEnd = scope.bitmapSize.width;
        const y = Math.round(item.y * scope.verticalPixelRatio) + 0.5;

        ctx.save();
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(xStart, y);
        ctx.lineTo(xEnd, y);
        ctx.stroke();

        if (item.label) {
          ctx.font = LABEL_FONT;
          ctx.fillStyle = item.color;
          ctx.textBaseline = "bottom";
          ctx.fillText(item.label, xStart + LABEL_PADDING, y - LABEL_PADDING);
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
    return new RayPaneRenderer(this.source.renderItems());
  }
}

/**
 * A series primitive drawing every `IndicatorLevel` a `levels`-output indicator
 * answered with — one instance per (id, params) result, its `levels` replaced
 * wholesale on every recompute rather than diffed, the same way a Line series'
 * `setData` replaces its points (task 3.9).
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
  private readonly views: readonly IPrimitivePaneView[] = [new RayPaneView(this)];

  constructor(color: string) {
    this.color = color;
  }

  setLevels(levels: readonly RayLevel[]): void {
    this.levels = levels;
  }

  setColor(color: string): void {
    this.color = color;
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

  /** Package-visible for `RayPaneView`, not the public API of this class. */
  renderItems(): RayRenderItem[] {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return [];
    const timeScale = chart.timeScale();
    return this.levels.map((level) => ({
      // `null` when `level.time` names no point the time scale currently knows —
      // a ray whose moment falls outside the loaded series draws nothing rather
      // than guessing a coordinate for it.
      x: timeScale.timeToCoordinate(level.time),
      y: series.priceToCoordinate(level.price),
      color: this.color,
      label: level.label,
    }));
  }
}
