import { useEffect, useRef, type RefObject } from "react";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import type { AgentChartDrawing } from "../agent/agentApi";
import { RayPrimitive } from "./RayPrimitive";
import { TrendlinePrimitive, type DrawnTrendline } from "./TrendlinePrimitive";
import { ZonePrimitive } from "./ZonePrimitive";
import { drawingColorFor, drawingColorFromToken, readChartColors, type ChartColors } from "./theme";
import type { Emphasis, MarkPalette } from "./drawingStyle";

/**
 * The objects standing on this instrument — levels, zones and trendlines — on primitives and a lifecycle
 * of their own, and on three triggers that must not be one: the list, the newest close, the picked-out id.
 */
export function useDrawingLayers({
  chartRef,
  seriesRef,
  colorsRef,
  drawnObjects,
  latestBar,
  selectedId,
}: {
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  colorsRef: RefObject<ChartColors | null>;
  /** What this chart draws — already filtered by the caller to the objects it can. */
  drawnObjects: readonly AgentChartDrawing[];
  latestBar: { close: number } | null;
  selectedId: number | null;
}): void {
  // Deliberately not the indicator maps above: that cleanup detaches whatever it does not recognise, and
  // a resolution change empties its results (design.md, "Rysunki i wskaźniki dzielą prymitywy, ale nie cykl życia").
  const drawingPrimitivesRef = useRef<
    Map<number, RayPrimitive | ZonePrimitive | TrendlinePrimitive>
  >(new Map());
  // The newest close, for a primitive built after the last candle arrived — the effect
  // that pushes it to the others runs on a different trigger than the one that builds them.
  const currentPriceRef = useRef<number | null>(null);

  // Keyed on `drawings` alone, so a resolution change leaves the objects where they were (`terminal-chart`
  // spec, "Zmiana rozdzielczości MUST zachować narysowane obiekty"); a symbol change hands over a new array.
  useEffect(() => {
    const chart = chartRef.current;
    const priceSeries = seriesRef.current;
    if (!chart || !priceSeries) return;
    const colors = colorsRef.current ?? readChartColors();
    const standing = drawnObjects;
    const live = new Set<number>();

    const palette: MarkPalette = {
      onFill: colors.surface,
      support: colors.up,
      resistance: colors.down,
    };
    const currentPrice = currentPriceRef.current;

    standing.forEach((drawing) => {
      live.add(drawing.id);
      // Derived from the drawing's own id, never from its place in the array, so removing the object
      // beside it repaints nothing (`terminal-chart` spec, "Kolor obiektu po usunięciu innego").
      const color = drawingColorFromToken(colors, drawing.color) ?? drawingColorFor(drawing.id, colors);
      const marks = { weight: "drawing" as const, objectId: String(drawing.id), palette };
      const existing = drawingPrimitivesRef.current.get(drawing.id);
      const geometry = drawing.geometry;

      if (geometry.kind === "level") {
        const ray = existing instanceof RayPrimitive ? existing : new RayPrimitive(color, marks);
        if (ray !== existing) {
          if (existing) priceSeries.detachPrimitive(existing);
          priceSeries.attachPrimitive(ray);
          drawingPrimitivesRef.current.set(drawing.id, ray);
        }
        ray.setColor(color);
        ray.setCurrentPrice(currentPrice);
        // Epoch 0 rather than the oldest drawn bar's time: `timeToX` snaps a moment with no bar to the
        // nearest one, so this follows the left edge as the pager reaches back instead of freezing at it.
        const from = geometry.at ?? 0;
        ray.setLevels([{ time: from as UTCTimestamp, price: geometry.price, label: drawing.label }]);
        return;
      }

      if (geometry.kind === "zone") {
        const zoneColors = { bullish: color, bearish: color, neutral: color };
        const zone =
          existing instanceof ZonePrimitive ? existing : new ZonePrimitive(zoneColors, marks);
        if (zone !== existing) {
          if (existing) priceSeries.detachPrimitive(existing);
          priceSeries.attachPrimitive(zone);
          drawingPrimitivesRef.current.set(drawing.id, zone);
        }
        // One colour in all three slots: a drawn zone is the operator's band, with no direction to
        // colour by the way an indicator's has.
        zone.setColors(zoneColors);
        zone.setCurrentPrice(currentPrice);
        zone.setZones([
          {
            from: (geometry.from ?? 0) as UTCTimestamp,
            to: geometry.to === null ? null : (geometry.to as UTCTimestamp),
            top: geometry.top,
            bottom: geometry.bottom,
            direction: null,
            label: drawing.label,
          },
        ]);
        return;
      }

      const line =
        existing instanceof TrendlinePrimitive ? existing : new TrendlinePrimitive(color, marks);
      if (line !== existing) {
        if (existing) priceSeries.detachPrimitive(existing);
        priceSeries.attachPrimitive(line);
        drawingPrimitivesRef.current.set(drawing.id, line);
      }
      line.setColor(color);
      line.setCurrentPrice(currentPrice);
      const drawn: DrawnTrendline = {
        from: geometry.a.time as UTCTimestamp,
        to: geometry.b.time as UTCTimestamp,
        fromPrice: geometry.a.price,
        toPrice: geometry.b.price,
        label: drawing.label,
        color: null,
      };
      line.setLines([drawn]);
    });

    for (const [id, primitive] of drawingPrimitivesRef.current) {
      if (live.has(id)) continue;
      priceSeries.detachPrimitive(primitive);
      drawingPrimitivesRef.current.delete(id);
    }
    // The three refs are the chart the caller owns; their identities never change.
  }, [drawnObjects, chartRef, seriesRef, colorsRef]);

  // The role its price-axis label announces is read off the newest candle, so a broken level stops calling
  // itself resistance (design.md, "Rola przelicza się z ostatniej świecy"). Its own effect: a tick rebuilds nothing.
  useEffect(() => {
    const price = latestBar?.close ?? null;
    currentPriceRef.current = price;
    for (const primitive of drawingPrimitivesRef.current.values()) primitive.setCurrentPrice(price);
  }, [latestBar]);

  // Picked out, or standing back for whatever is (`terminal-chart-objects` spec, "Wskazany obiekt widać,
  // że jest wskazany"). Touches only how heavily an object is drawn, never what it is.
  useEffect(() => {
    for (const [id, primitive] of drawingPrimitivesRef.current) {
      const emphasis: Emphasis =
        selectedId === null ? "normal" : id === selectedId ? "selected" : "dimmed";
      primitive.setEmphasis(emphasis);
    }
  }, [selectedId, drawnObjects]);
}
