import { useEffect, useRef, type RefObject } from "react";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import type { AgentChartDrawing } from "../agent/agentApi";
import { RayPrimitive } from "./RayPrimitive";
import { TrendlinePrimitive, type DrawnTrendline } from "./TrendlinePrimitive";
import { ZonePrimitive } from "./ZonePrimitive";
import { drawingColorFor, drawingColorFromToken, readChartColors, type ChartColors } from "./theme";
import type { Emphasis, MarkPalette } from "./drawingStyle";

/**
 * The objects standing on this instrument — levels, zones and trendlines — on their own
 * primitives and their own lifecycle.
 *
 * Separate from the indicator layers on purpose, and not only for tidiness: the indicator
 * cleanup detaches whatever it does not recognise as an active instance, and a resolution
 * change empties the indicator results deliberately. Sharing one map would be a line of
 * code and a bug that looks like the operator's supports vanishing (design.md, "Rysunki i
 * wskaźniki dzielą prymitywy, ale nie cykl życia").
 *
 * Three effects, on three triggers that must not be one: what the objects *are* (the
 * list), what price they are being read against (the newest close, which moves on every
 * forming candle and must rebuild nothing), and which one is picked out.
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
  // The drawings' own three primitives, in their own refs — deliberately not the maps
  // above. Sharing them would be one line of code and one bug that looks like supports
  // vanishing: the indicator cleanup detaches whatever it does not recognise as an
  // active instance, and a resolution change empties `indicatorsState.results` on
  // purpose (design.md, "Rysunki i wskaźniki dzielą prymitywy, ale nie cykl życia").
  // Keyed by the drawing's own id, one primitive each: `RayPrimitive` and `ZonePrimitive`
  // hold one colour for everything they draw, and every drawing carries its own.
  const drawingPrimitivesRef = useRef<
    Map<number, RayPrimitive | ZonePrimitive | TrendlinePrimitive>
  >(new Map());
  // The newest close, for a primitive built after the last candle arrived — the effect
  // that pushes it to the others runs on a different trigger than the one that builds them.
  const currentPriceRef = useRef<number | null>(null);

  // --- drawings: the objects standing on this instrument, on their own primitives and
  // their own lifecycle. Keyed on `drawings` alone, so a resolution change leaves them
  // exactly where they were — the effect above cannot reach them, and this one has no
  // reason to run (`terminal-chart` spec, "Zmiana rozdzielczości MUST zachować narysowane
  // obiekty"). A symbol change replaces them because the caller reads a different
  // instrument's list and hands over a different array.
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
      // The drawing's own colour, or one the chart derives from its id — never from where
      // it stands in this array, so removing the object beside it repaints nothing
      // (`terminal-chart` spec, "Kolor obiektu po usunięciu innego").
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
        // A null `at` means the level has always been in effect. Sent as epoch 0 rather
        // than as the oldest drawn bar's own time: `timeToX` snaps a moment with no bar
        // to the nearest one, so this resolves to the left edge of whatever is loaded and
        // keeps doing so as the pager reaches further back — where a time read once here
        // would freeze at whichever bar happened to be oldest at the time.
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
        // One colour in all three slots: a drawn zone has no direction to colour by, the
        // way an indicator's does — it is the operator's band, not a bullish or bearish
        // reading of one.
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

  // The role its price-axis label announces is read off the newest candle, so it follows
  // the market on its own: a level the price breaks through stops calling itself
  // resistance (design.md, "Rola przelicza się z ostatniej świecy"). Its own effect
  // rather than a dependency of the one above — a forming candle must not rebuild
  // anything, only hand over a number.
  useEffect(() => {
    const price = latestBar?.close ?? null;
    currentPriceRef.current = price;
    for (const primitive of drawingPrimitivesRef.current.values()) primitive.setCurrentPrice(price);
  }, [latestBar]);

  // Picked out, or standing back for whatever is (`terminal-chart-objects` spec, "Wskazany
  // obiekt widać, że jest wskazany"). Nothing here touches what the object *is* — only
  // how heavily it is drawn.
  useEffect(() => {
    for (const [id, primitive] of drawingPrimitivesRef.current) {
      const emphasis: Emphasis =
        selectedId === null ? "normal" : id === selectedId ? "selected" : "dimmed";
      primitive.setEmphasis(emphasis);
    }
  }, [selectedId, drawnObjects]);
}
