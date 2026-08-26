import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { readChartColors } from "../chart/theme";
import { formatCrosshairTime } from "../ui/formatTime";
import type { History } from "./polymarketApi";
import { toLineData } from "./series";

/**
 * One outcome over time, in its own chart: the candle chart carries four prices, drawings and an agent surface,
 * this one a single value. The scale is pinned to 0..1 and the coverage boundary is drawn — both requirements.
 */
export function ProbabilityChart({
  history,
  label,
}: {
  history: History;
  /** What the line is of — shown on the boundary marker, which is the one place the chart
   *  says whose series this is. */
  label: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const [boundaryX, setBoundaryX] = useState<number | null>(null);

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
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      rightPriceScale: { borderColor: colors.axis },
      localization: {
        timeFormatter: (time: Time) => formatCrosshairTime(time as number),
        // The axis speaks in percent because that is what the rest of the tab shows, off the same 0..1
        // value — the multiplication happens once per surface, and this is the chart's.
        priceFormatter: (price: number) => `${(price * 100).toFixed(1)}%`,
      },
      timeScale: { borderColor: colors.axis, timeVisible: true, secondsVisible: false },
      autoSize: false,
      width: container.clientWidth,
      height: container.clientHeight,
    });

    const series = chart.addSeries(LineSeries, {
      color: colors.axis,
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
      // Pinned rather than autoscaled. `autoscaleInfoProvider` is what fixes a range in
      // this library; `autoScale: false` alone leaves whatever range happened to be set.
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 1 },
      }),
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () =>
      chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    series.setData(toLineData(history.points));
    chart.timeScale().fitContent();

    const { collectedFrom } = history;
    if (collectedFrom === null) {
      setBoundaryX(null);
      return;
    }

    // Positioned from the time scale rather than from the data, so it lands correctly even when the
    // boundary falls outside the drawn points — which is exactly the case it exists for.
    const place = () => {
      const x = chart
        .timeScale()
        .timeToCoordinate(Math.floor(collectedFrom.getTime() / 1000) as Time);
      setBoundaryX(x === null ? null : Number(x));
    };
    place();
    const scale = chart.timeScale();
    scale.subscribeVisibleTimeRangeChange(place);
    return () => scale.unsubscribeVisibleTimeRangeChange(place);
  }, [history]);

  const empty = history.points.length === 0;

  return (
    <div className="relative h-64 w-full">
      <div ref={containerRef} className="h-full w-full" />

      {boundaryX !== null && (
        <div
          className="pointer-events-none absolute inset-y-0 flex items-start"
          style={{ left: `${boundaryX}px` }}
        >
          <div className="h-full border-l border-dashed border-warning/70" />
          <span className="mt-1 ml-1 rounded bg-panel/90 px-1 text-[10px] whitespace-nowrap text-warning">
            collected from here — nothing older exists for {label}
          </span>
        </div>
      )}

      {empty && (
        <p className="absolute inset-0 flex items-center justify-center text-xs text-ink-faint">
          Nothing has been collected for this outcome yet.
        </p>
      )}
    </div>
  );
}
