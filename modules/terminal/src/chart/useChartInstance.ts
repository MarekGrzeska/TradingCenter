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
 * Created once, torn down once, never re-created for data. Every hook that draws onto it must be declared
 * below; its cleanup takes `clearIndicatorLayers` as a **ref**, since a dependency array reads during render.
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
      // Both formatters read Warsaw's calendar instead of the library's own UTC one — the labels only,
      // never the timestamps (design.md, "Strefa: formatowanie, nie przesuwanie znaczników").
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
      // The library's price-axis label is sourced from the last *visible* bar whatever `priceLineSource`
      // says, so panning into history announced that bar's price. The chart draws its own at the newest candle.
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

    // Panning towards the left edge is the whole trigger for loading older candles. How much is not decided
    // here: the pager asks until `needsMore` says the margin is filled, which stops it looping on frame correction.
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
      // Both refs are read here rather than copied when the effect ran — the opposite of what
      // `exhaustive-deps` asks — because what matters is whatever is current at unmount.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      onVisibleRangeChangeRef.current?.(null);
      chartRef.current = null;
      seriesRef.current = null;
      // The line belonged to the series that just went away with the chart.
      priceLineRef.current = null;
      // `chart.remove()` already freed every series, pane, level, marker and primitive; this only stops
      // the sync effect from reaching for one that is gone.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      clearIndicatorLayersRef.current();
    };
    // Empty on purpose: one chart per mount. Every ref above is stable, and the one thing that is not —
    // what to clear on the way out — is reached through a ref for exactly that reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
