import { useLayoutEffect, type RefObject } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type Time,
  type TickMarkType,
} from "lightweight-charts";

import { formatCrosshairTime, formatTickMark } from "../ui/formatTime";
import type { Bar } from "../data/types";
import { OLDER_MARGIN_BARS, toCandlestick } from "./chartWindow";
import type { BarsRange } from "./indicators/useIndicators";
import { candlestickColors, readChartColors, type ChartColors } from "./theme";

/** The price pane's own stretch factor, set once at chart creation so an
 *  own-pane oscillator added later does not grow to the price chart's own
 *  height — `lightweight-charts`' default (equal stretch for every pane) reads
 *  as "RSI is as important as the candles" the moment a second pane exists. */
const PRICE_PANE_STRETCH = 4;

/**
 * The chart instance itself: created once, torn down once, and never re-created for
 * data. Everything else in `Chart.tsx` finds it through `chartRef`.
 *
 * **Where this has to be called, and why it is not obvious.** Effects run in the order
 * they were declared, so every hook that draws *onto* the chart — the indicator layers,
 * the drawing layers — must be declared below this call, or its first run finds no chart
 * to draw on. That constraint used to make this effect impossible to move: its cleanup
 * calls `clearIndicatorLayers`, which comes from one of those hooks below, and naming it
 * in the dependency array read it before it existed. Listing it, as
 * `react-hooks/exhaustive-deps` asked, took all 121 chart tests down at once.
 *
 * `clearIndicatorLayers` arrives as a **ref** instead, which is what unties it: a
 * dependency array is read during render, and a ref's contents are not. The component
 * fills it after the layers hook has returned, and this cleanup — which runs at unmount,
 * long after — reads whatever is in it by then. Same node, solved from the other side.
 */
export function useChartInstance({
  containerRef,
  chartRef,
  seriesRef,
  colorsRef,
  barsRef,
  priceLineRef,
  requestOlderRef,
  syncIndicatorWindowRef,
  onVisibleRangeChangeRef,
  clearIndicatorLayersRef,
}: {
  containerRef: RefObject<HTMLDivElement | null>;
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  colorsRef: RefObject<ChartColors | null>;
  barsRef: RefObject<Bar[]>;
  priceLineRef: RefObject<IPriceLine | null>;
  /** Panning towards the left edge asks the pager for more. */
  requestOlderRef: RefObject<() => void>;
  syncIndicatorWindowRef: RefObject<() => void>;
  onVisibleRangeChangeRef: RefObject<((range: BarsRange | null) => void) | undefined>;
  /** Filled by the component *after* the indicator-layer hook below has returned — see
   *  the note above on why this is a ref and not the function itself. */
  clearIndicatorLayersRef: RefObject<() => void>;
}): void {
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = readChartColors();
    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: colors.surface },
        textColor: colors.inkMuted,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.axis },
      // Both formatters read Warsaw's calendar instead of the library's own UTC one —
      // the candles' timestamps are untouched, only their labels (design.md, "Strefa:
      // formatowanie, nie przesuwanie znaczników").
      localization: {
        timeFormatter: (time: Time) => formatCrosshairTime(time as number),
      },
      timeScale: {
        borderColor: colors.axis,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) =>
          formatTickMark(time as number, tickMarkType),
      },
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: false,
      width: container.clientWidth,
      height: container.clientHeight,
    });
    const series = chart.addSeries(CandlestickSeries, {
      ...candlestickColors(colors),
      // Both of the series' own price markers are off, and one of them is the
      // point: the price-axis label the library draws is sourced from the last
      // *visible* bar (`SeriesPriceAxisView` asks for `lastValueData(false)`,
      // whatever `priceLineSource` says), so panning into history left the
      // right-hand scale announcing the price of whatever candle happened to be
      // at the edge of the viewport. The chart draws its own instead, always at
      // the newest candle.
      lastValueVisible: false,
      priceLineVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = series;
    colorsRef.current = colors;
    chart.panes()[0]?.setStretchFactor(PRICE_PANE_STRETCH);

    // Whatever the feed already delivered before this effect re-ran (a
    // StrictMode remount, most often) is redrawn rather than lost.
    if (barsRef.current.length > 0) {
      series.setData(barsRef.current.map(toCandlestick));
      chart.timeScale().fitContent();
    }

    // Panning towards the left edge of what is drawn is the whole trigger for
    // loading older candles (terminal-chart spec, "Wykres dociąga starszą
    // historię przy przewijaniu w lewo"). How much gets loaded is not decided
    // here: the pager keeps asking until `needsMore` says the margin is
    // filled, which is what stops it looping on its own frame correction.
    const onRangeChange = (range: LogicalRange | null) => {
      if (range && range.from < OLDER_MARGIN_BARS) requestOlderRef.current();
      // Panning off the computed window is what asks for a new one — the operator who
      // jumped to March needs indicators over March, not over the whole series behind it.
      syncIndicatorWindowRef.current();

      const series = barsRef.current;
      const fromIndex = range ? Math.max(0, Math.round(range.from)) : -1;
      const toIndex = range ? Math.min(series.length - 1, Math.round(range.to)) : -1;
      const fromTime = series[fromIndex]?.time;
      const toTime = series[toIndex]?.time;
      onVisibleRangeChangeRef.current?.(
        fromTime !== undefined && toTime !== undefined ? { from: fromTime, to: toTime } : null,
      );
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        chart.resize(width, height);
      }
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      chart.remove();
      // Both refs below are read here rather than copied into a variable when the effect
      // ran, which is what `react-hooks/exhaustive-deps` asks for and is the opposite of
      // what these two want: the value that matters is whatever is current at unmount —
      // the parent's latest callback, and a clear function that did not exist yet when
      // this effect started.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      onVisibleRangeChangeRef.current?.(null);
      chartRef.current = null;
      seriesRef.current = null;
      // The line belonged to the series that just went away with the chart.
      priceLineRef.current = null;
      // Every indicator series, pane, reference level, marker plugin and
      // primitive belonged to it too — `chart.remove()` already freed them,
      // this only stops the sync effect from reaching for one that is gone.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      clearIndicatorLayersRef.current();
    };
    // Empty on purpose: one chart per mount. Every ref above is stable, and the one
    // thing that is not a ref — what to clear on the way out — is reached through one
    // for exactly that reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
