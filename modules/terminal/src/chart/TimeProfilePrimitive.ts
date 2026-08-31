import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

/**
 * One price bucket of a `time_profile` result. `VAH`/`VAL` are summary edges, not buckets, and never
 * reach this primitive — what is asked for is the histogram itself, not its boundary annotations.
 */
export interface ProfileBar {
  price: number;
  count: number;
  isPointOfControl: boolean;
}

export interface ProfileColors {
  bar: string;
  pointOfControl: string;
}

interface ProfileRenderItem {
  y: number | null;
  /** 0..1 — this bucket's count against the busiest one in the same result. */
  share: number;
  color: string;
}

/** How far the longest bar reaches into the pane, as a fraction of its width —
 *  a profile is read beside the candles, not instead of them. */
const MAX_BAR_WIDTH_FRACTION = 0.22;
const BAR_THICKNESS_PX = 3;

class ProfilePaneRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly ProfileRenderItem[];

  constructor(items: readonly ProfileRenderItem[]) {
    this.items = items;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const xEnd = scope.bitmapSize.width;
      const maxWidth = xEnd * MAX_BAR_WIDTH_FRACTION;
      const thickness = BAR_THICKNESS_PX * scope.verticalPixelRatio;

      for (const item of this.items) {
        if (item.y === null) continue;
        const y = item.y * scope.verticalPixelRatio;
        const width = item.share * maxWidth;

        ctx.fillStyle = item.color;
        ctx.fillRect(xEnd - width, y - thickness / 2, width, thickness);
      }
    });
  }
}

class ProfilePaneView implements IPrimitivePaneView {
  private readonly source: TimeProfilePrimitive;

  constructor(source: TimeProfilePrimitive) {
    this.source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new ProfilePaneRenderer(this.source.renderItems());
  }
}

/**
 * `time_profile`'s buckets as a horizontal histogram against the pane's right edge, each bar's length set by
 * its count against the busiest bucket in the same read, so the point of control always reaches full width.
 */
export class TimeProfilePrimitive implements ISeriesPrimitive<Time> {
  private bars: readonly ProfileBar[] = [];
  private colors: ProfileColors;
  private series: ISeriesApi<SeriesType, Time> | null = null;
  private readonly views: readonly IPrimitivePaneView[] = [new ProfilePaneView(this)];

  constructor(colors: ProfileColors) {
    this.colors = colors;
  }

  setBars(bars: readonly ProfileBar[]): void {
    this.bars = bars;
  }

  setColors(colors: ProfileColors): void {
    this.colors = colors;
  }

  attached({ series }: SeriesAttachedParameter<Time>): void {
    this.series = series;
  }

  detached(): void {
    this.series = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Package-visible for `ProfilePaneView`, not the public API of this class. */
  renderItems(): ProfileRenderItem[] {
    const series = this.series;
    if (!series) return [];
    const maxCount = this.bars.reduce((max, bar) => Math.max(max, bar.count), 0);
    if (maxCount <= 0) return [];

    return this.bars.map((bar) => ({
      y: series.priceToCoordinate(bar.price),
      share: bar.count / maxCount,
      color: bar.isPointOfControl ? this.colors.pointOfControl : this.colors.bar,
    }));
  }
}
