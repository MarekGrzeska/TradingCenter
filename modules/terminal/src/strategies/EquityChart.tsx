import { useEffect, useRef } from "react";
import { AreaSeries, ColorType, LineSeries, createChart, type Time } from "lightweight-charts";
import { readChartColors } from "../chart/theme";
import { formatCrosshairTime } from "../ui/formatTime";
import { drawdownPoints, equityPoints } from "./curve";

/** Equity at each UTC midnight of the run, and the drawdown from its running peak in a pane below. */
export function EquityChart({
  equity,
  capital,
}: {
  equity: readonly (readonly [number, number | null])[];
  capital: number;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    const colors = readChartColors();
    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: colors.surface }, textColor: colors.inkMuted, attributionLogo: false },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      localization: { timeFormatter: (time: Time) => formatCrosshairTime(time as number) },
      timeScale: { borderColor: colors.axis },
      rightPriceScale: { borderColor: colors.axis },
      autoSize: true,
    });
    const points = equityPoints(equity);
    chart
      .addSeries(LineSeries, { color: colors.indicatorLines[0], lineWidth: 2, title: "kapitał" })
      .setData(points.map((p) => ({ time: p.time as Time, value: p.value })));
    chart
      .addSeries(
        AreaSeries,
        { lineColor: colors.down, topColor: "transparent", bottomColor: colors.down, title: "obsunięcie", priceFormat: { type: "percent" } },
        1,
      )
      .setData(drawdownPoints(points, capital).map((p) => ({ time: p.time as Time, value: p.value * 100 })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [equity, capital]);

  return <div ref={host} className="h-64 w-full" aria-label="Krzywa kapitału" />;
}
