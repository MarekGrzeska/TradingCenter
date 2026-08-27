import type {
  IChartApi,
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
  defaultMarkPalette,
  type Emphasis,
  type MarkOptions,
  type MarkPalette,
  type MarkWeight,
} from "./drawingStyle";

/** One price the axis should announce, and the colour to announce it in. The colour is a
 *  function rather than a value because it is read at paint time: a level recoloured
 *  without its set of prices changing must repaint, and nothing rebuilds these then. */
export interface AxisEntry {
  price: number;
  color(): string;
}

/**
 * What every mark — a ray, a zone, a trend line — is made of. The three primitives held the same fifty lines
 * each, and only three things differed: what the shape draws, where a click lands, which prices it announces.
 */
export abstract class MarkPrimitive<Item> implements ISeriesPrimitive<Time> {
  protected chart: IChartApi | null = null;
  protected series: ISeriesApi<SeriesType, Time> | null = null;
  protected currentPrice: number | null = null;
  private requestUpdate: (() => void) | null = null;
  private axisViews: readonly ISeriesPrimitiveAxisView[] = [];

  readonly markWeight: MarkWeight;
  /** The operator's own object, or `null` for an indicator's mark — which is what keeps
   *  a `level_clusters` chart from filling the axis with labels and from being clickable
   *  (`terminal-chart-objects` spec, "Operator wskazuje obiekt na wykresie"). */
  readonly objectId: string | null;
  readonly palette: MarkPalette;
  emphasis: Emphasis = "normal";

  constructor(options: MarkOptions = {}) {
    this.markWeight = options.weight ?? "indicator";
    this.objectId = options.objectId ?? null;
    this.palette = options.palette ?? defaultMarkPalette();
  }

  /** The pane view drawing this shape. A subclass field, because a view is built with
   *  `this` and nothing here can do that for it. */
  protected abstract readonly views: readonly IPrimitivePaneView[];

  /** Package-visible for the subclass' own pane view, not the public API of the class. */
  abstract renderItems(): Item[];

  /** Every shape carries its own tolerance, because every shape has one: a band's area
   *  is its own, a line needs a margin around it (design.md, "Tolerancja trafienia
   *  mieszka w `hitTest` każdego prymitywu"). */
  abstract hitTest(x: number, y: number): PrimitiveHoveredItem | null;

  /** The prices this mark announces on the axis, in the order they should appear. */
  protected abstract axisEntries(): AxisEntry[];

  /** The newest close, for the axis label's role — a level the price breaks through stops
   *  calling itself resistance. Null while the chart has drawn no candle. */
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

  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return this.axisViews;
  }

  /** Called by a subclass whenever the set of prices it draws has changed — a fresh array
   *  only then, since the library caches these by reference and rebuilding one per repaint
   *  would defeat that. */
  protected rebuildAxisViews(): void {
    if (this.objectId === null) {
      this.axisViews = [];
      return;
    }
    this.axisViews = this.axisEntries().map(
      (entry) =>
        new DrawingPriceAxisView(() => ({
          coordinate: this.series?.priceToCoordinate(entry.price) ?? null,
          price: entry.price,
          color: entry.color(),
          currentPrice: this.currentPrice,
          palette: this.palette,
        })),
    );
  }
}
