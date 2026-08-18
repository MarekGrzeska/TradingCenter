import { useCallback, useEffect, useRef, type RefObject } from "react";
import {
  HistogramSeries,
  LineSeries,
  LineStyle,
  createSeriesMarkers,
  type IChartApi,
  type IPaneApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type HistogramData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import type { IndicatorCatalogueEntry } from "../data/types";
import { RayPrimitive } from "./RayPrimitive";
import { TimeProfilePrimitive, type ProfileBar } from "./TimeProfilePrimitive";
import { ZonePrimitive, type DrawnZone } from "./ZonePrimitive";
import { assignLineColors, drawnInstances } from "./chartLines";
import type { useIndicators } from "./indicators/useIndicators";
import { readChartColors, type ChartColors } from "./theme";

const OWN_PANE_STRETCH = 1;

/**
 * Every indicator instance the operator chose, drawn and kept in step with what the
 * archive last answered.
 *
 * One series, pane, marker plugin or primitive per instance — keyed by the instance, so
 * the same catalogue entry chosen twice draws twice, and changing one instance's period
 * moves its own line rather than tearing a series down and building it again. The maps
 * live here rather than in `Chart.tsx` because nothing else may touch them: the drawings
 * keep their own primitives on purpose, and sharing these would be one line of code and
 * one bug that looks like supports vanishing (design.md, "Rysunki i wskaźniki dzielą
 * prymitywy, ale nie cykl życia").
 *
 * `clear()` is what the chart's own teardown calls: `chart.remove()` has already freed
 * all of this, and emptying the maps only stops the effect from reaching for a series
 * that is gone.
 */
export function useIndicatorLayers({
  chartRef,
  seriesRef,
  colorsRef,
  indicatorsState,
  catalogueById,
  instanceColors,
}: {
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  colorsRef: RefObject<ChartColors | null>;
  indicatorsState: ReturnType<typeof useIndicators>;
  catalogueById: Map<string, IndicatorCatalogueEntry>;
  /** The colour each instance was given by hand, by instance key. */
  instanceColors: Map<string, string | null>;
}): { clear(): void } {
  // One series per (indicator, params, line key) — Line unless the line asks for
  // a histogram (MACD's, so far) — see the sync effect below.
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<"Line"> | ISeriesApi<"Histogram">>>(
    new Map(),
  );
  // One pane per (indicator, params) whose `render.pane` is "own" — RSI and MACD
  // each get their own row, the way every other charting platform draws them,
  // rather than sharing one oscillator pane between indicators that disagree
  // about scale.
  const ownPanesRef = useRef<Map<string, IPaneApi<Time>>>(new Map());
  // The catalogue's reference-level hint (RSI's 30/70, …) drawn once per
  // (indicator, params) rather than recomputed every render — the levels never
  // change while the selection is active, only the lines they sit behind do.
  const levelLinesRef = useRef<
    Map<string, { series: ISeriesApi<"Line"> | ISeriesApi<"Histogram">; lines: IPriceLine[] }>
  >(new Map());
  // One `createSeriesMarkers` plugin per (indicator, params) whose output is
  // `markers` — `swing_points`, so far — attached to the price series, since
  // `canDrawIndicator` only offers markers/levels entries drawn on it.
  const markerPluginsRef = useRef<Map<string, ISeriesMarkersPluginApi<Time>>>(new Map());
  // One `RayPrimitive` per (indicator, params) whose output is `levels` and
  // whose `render.style` is not `"histogram"` — `htf_levels_*`, `pivots_*`,
  // `level_clusters` — replacing its levels wholesale on every recompute
  // rather than being torn down and rebuilt.
  const rayPrimitivesRef = useRef<Map<string, RayPrimitive>>(new Map());
  // One `ZonePrimitive` per (indicator, params) whose output is `zones` —
  // `range_gap`, `body_gap`, `session_range_*`, `opening_range` (task 4.7).
  const zonePrimitivesRef = useRef<Map<string, ZonePrimitive>>(new Map());
  // One `TimeProfilePrimitive` per (indicator, params) whose output is
  // `levels` with `render.style === "histogram"` — `time_profile`, the one
  // entry that draws a histogram rather than reference rays (task 5.4).
  const timeProfilePrimitivesRef = useRef<Map<string, TimeProfilePrimitive>>(new Map());

  // --- indicators: one Line series per (instance, line key), synced to what the archive
  // last answered. A price-pane entry draws on the candles' own pane; an own-pane entry
  // (RSI, ATR, MACD, …) gets a pane of its own, one per instance rather than one shared
  // by every oscillator — see `canDrawIndicator`. Keyed by the instance, so the same
  // entry chosen twice draws twice and changing one instance's period moves its own line
  // rather than tearing a series down and building it again.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const colors = colorsRef.current ?? readChartColors();

    const active = new Set<string>();
    const activeOwnPanes = new Set<string>();
    const activeResults = new Set<string>();

    // The snapshot's own pairing: `results[i]` answers `selections[i]`
    // (`market-data-indicators` spec, "Kolejność wyników"). Nothing else binds the two —
    // two instances of one entry with the same params are identical on the wire.
    const drawable = drawnInstances(
      indicatorsState.selections,
      indicatorsState.results,
      catalogueById,
    );
    const lineColors = assignLineColors(drawable, colors, instanceColors);

    for (const { selection, result, entry } of drawable) {
      const ownPaneKey = selection.key;
      const colorsForInstance = lineColors.get(selection.key) ?? colors.indicatorLines;

      if (entry.output === "markers") {
        if (!result.markers) continue;
        activeResults.add(ownPaneKey);
        const priceSeries = seriesRef.current;
        if (!priceSeries) continue;
        const color = colorsForInstance[0];
        const markers: SeriesMarker<Time>[] = result.markers.map((point) =>
          point.price === null
            ? { time: point.time as UTCTimestamp, position: "inBar", shape: "circle", color, text: point.label }
            : {
                time: point.time as UTCTimestamp,
                position: "atPriceMiddle",
                price: point.price,
                shape: "circle",
                color,
                text: point.label,
              },
        );
        let plugin = markerPluginsRef.current.get(ownPaneKey);
        if (!plugin) {
          plugin = createSeriesMarkers(priceSeries, []);
          markerPluginsRef.current.set(ownPaneKey, plugin);
        }
        plugin.setMarkers(markers);
        continue;
      }

      if (entry.output === "levels" && entry.render.style === "histogram") {
        // `time_profile`, so far the only entry that pairs the two — a
        // histogram panel instead of the reference rays every other `levels`
        // entry draws (task 5.4).
        if (!result.levels) continue;
        activeResults.add(ownPaneKey);
        const priceSeries = seriesRef.current;
        if (!priceSeries) continue;
        // `indicatorLines[0]` is `--color-accent` — the categorical palette's
        // first slot (`theme.ts`), reused here rather than drawing from the
        // per-line cycle: the point of control is one highlight, not a series
        // of same-role lines that need to stay distinguishable from each other.
        const profileColors = { bar: colors.inkMuted, pointOfControl: colors.indicatorLines[0] };
        let profile = timeProfilePrimitivesRef.current.get(ownPaneKey);
        if (!profile) {
          profile = new TimeProfilePrimitive(profileColors);
          priceSeries.attachPrimitive(profile);
          timeProfilePrimitivesRef.current.set(ownPaneKey, profile);
        }
        profile.setColors(profileColors);
        // `VAH`/`VAL` carry `count: null` — summary edges, not buckets, and
        // the histogram itself has nothing to draw for them (`ProfileBar`'s
        // own doc).
        const bars: ProfileBar[] = result.levels
          .filter((level) => level.count !== null)
          .map((level) => ({
            price: level.price,
            count: level.count as number,
            isPointOfControl: level.label === "POC",
          }));
        profile.setBars(bars);
        continue;
      }

      if (entry.output === "levels") {
        if (!result.levels) continue;
        activeResults.add(ownPaneKey);
        const priceSeries = seriesRef.current;
        if (!priceSeries) continue;
        const color = colorsForInstance[0];
        let ray = rayPrimitivesRef.current.get(ownPaneKey);
        if (!ray) {
          ray = new RayPrimitive(color);
          priceSeries.attachPrimitive(ray);
          rayPrimitivesRef.current.set(ownPaneKey, ray);
        }
        ray.setColor(color);
        ray.setLevels(
          result.levels.map((level) => ({
            time: level.from as UTCTimestamp,
            price: level.price,
            label: level.label,
          })),
        );
        continue;
      }

      if (entry.output === "zones") {
        if (!result.zones) continue;
        activeResults.add(ownPaneKey);
        const priceSeries = seriesRef.current;
        if (!priceSeries) continue;
        let zonePrimitive = zonePrimitivesRef.current.get(ownPaneKey);
        if (!zonePrimitive) {
          zonePrimitive = new ZonePrimitive({ bullish: colors.up, bearish: colors.down, neutral: colors.inkMuted });
          priceSeries.attachPrimitive(zonePrimitive);
          zonePrimitivesRef.current.set(ownPaneKey, zonePrimitive);
        }
        zonePrimitive.setColors({ bullish: colors.up, bearish: colors.down, neutral: colors.inkMuted });
        const zones: DrawnZone[] = result.zones.map((zone) => ({
          from: zone.from as UTCTimestamp,
          to: zone.to === null ? null : (zone.to as UTCTimestamp),
          top: zone.top,
          bottom: zone.bottom,
          direction: zone.direction,
        }));
        zonePrimitive.setZones(zones);
        continue;
      }

      // entry.output === "lines" from here on — `canDrawIndicator` refuses
      // every other combination.
      if (!result.lines) continue;
      activeResults.add(ownPaneKey);

      let paneIndex: number | undefined;
      if (entry.render.pane === "own") {
        activeOwnPanes.add(ownPaneKey);
        let pane = ownPanesRef.current.get(ownPaneKey);
        if (!pane) {
          // `preserveEmptyPane: true` — without it, the chart removes a pane
          // on its own the moment its last series does (`IPaneApi.
          // preserveEmptyPane` docs), racing the explicit `chart.removePane`
          // below: deselecting one of two own-pane indicators left the other's
          // pane index stale and threw. This keeps removal singly-owned, by
          // the cleanup loop, which already knows to look up a live index.
          pane = chart.addPane(true);
          pane.setStretchFactor(OWN_PANE_STRETCH);
          ownPanesRef.current.set(ownPaneKey, pane);
        }
        paneIndex = pane.paneIndex();
      }

      let firstLine: ISeriesApi<"Line"> | ISeriesApi<"Histogram"> | undefined;
      const lines = result.lines;

      entry.lines.forEach((lineSpec, lineIndex) => {
        const key = `${selection.key}|${lineSpec.key}`;
        active.add(key);
        const values = lines[lineSpec.key] ?? [];
        // A line overrides the entry's own style for itself alone — MACD's
        // histogram sitting beside two ordinary lines in the same entry.
        const style = lineSpec.style ?? entry.render.style;

        let series = indicatorSeriesRef.current.get(key);
        if (style === "histogram") {
          const points: (HistogramData<Time> | WhitespaceData<Time>)[] = indicatorsState.times.map(
            (time, i) => {
              const value = values[i];
              return value === null || value === undefined
                ? { time: time as UTCTimestamp }
                : { time: time as UTCTimestamp, value, color: value >= 0 ? colors.up : colors.down };
            },
          );
          if (!series) {
            series = chart.addSeries(
              HistogramSeries,
              {
                lastValueVisible: false,
                priceLineVisible: false,
                ...(entry.render.autoscale ? {} : { autoscaleInfoProvider: () => null }),
              },
              paneIndex,
            );
            indicatorSeriesRef.current.set(key, series);
          }
          series.setData(points);
        } else {
          const points: (LineData<Time> | WhitespaceData<Time>)[] = indicatorsState.times.map(
            (time, i) => {
              const value = values[i];
              return value === null || value === undefined
                ? { time: time as UTCTimestamp }
                : { time: time as UTCTimestamp, value };
            },
          );
          if (!series) {
            series = chart.addSeries(
              LineSeries,
              {
                color: colorsForInstance[lineIndex],
                lineWidth: 1,
                lastValueVisible: false,
                priceLineVisible: false,
                ...(entry.render.autoscale ? {} : { autoscaleInfoProvider: () => null }),
              },
              paneIndex,
            );
            indicatorSeriesRef.current.set(key, series);
          } else {
            // Recolouring an instance is not a recompute: the operator picks a swatch and
            // the line it stands for changes on the spot, without another read.
            series.applyOptions({ color: colorsForInstance[lineIndex] });
          }
          series.setData(points);
        }
        firstLine ??= series;
      });

      // Reference levels (RSI's 30/70, …) — drawn once per instance on whichever
      // line happens to be first, since every line an entry declares shares that
      // pane's one price scale.
      const anchor = firstLine;
      if (entry.render.levels.length > 0 && anchor && !levelLinesRef.current.has(ownPaneKey)) {
        const priceLines = entry.render.levels.map((level) =>
          anchor.createPriceLine({
            price: level,
            color: colors.inkMuted,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "",
          }),
        );
        levelLinesRef.current.set(ownPaneKey, { series: anchor, lines: priceLines });
      }
    }

    for (const [key, line] of indicatorSeriesRef.current) {
      if (active.has(key)) continue;
      chart.removeSeries(line);
      indicatorSeriesRef.current.delete(key);
    }

    for (const [ownPaneKey, pane] of ownPanesRef.current) {
      if (activeOwnPanes.has(ownPaneKey)) continue;
      // Belt and braces alongside `preserveEmptyPane: true` above: a pane
      // already gone (by whatever path) must not be handed to `removePane`
      // again — that is what actually threw.
      if (chart.panes().includes(pane)) chart.removePane(pane.paneIndex());
      ownPanesRef.current.delete(ownPaneKey);
    }

    for (const [key, { series, lines }] of levelLinesRef.current) {
      if (activeResults.has(key)) continue;
      for (const priceLine of lines) series.removePriceLine(priceLine);
      levelLinesRef.current.delete(key);
    }

    for (const [key, plugin] of markerPluginsRef.current) {
      if (activeResults.has(key)) continue;
      plugin.detach();
      markerPluginsRef.current.delete(key);
    }

    for (const [key, ray] of rayPrimitivesRef.current) {
      if (activeResults.has(key)) continue;
      seriesRef.current?.detachPrimitive(ray);
      rayPrimitivesRef.current.delete(key);
    }

    for (const [key, zonePrimitive] of zonePrimitivesRef.current) {
      if (activeResults.has(key)) continue;
      seriesRef.current?.detachPrimitive(zonePrimitive);
      zonePrimitivesRef.current.delete(key);
    }

    for (const [key, profile] of timeProfilePrimitivesRef.current) {
      if (activeResults.has(key)) continue;
      seriesRef.current?.detachPrimitive(profile);
      timeProfilePrimitivesRef.current.delete(key);
    }
    // The three refs are the chart the caller owns; their identities never change.
  }, [
    indicatorsState.results,
    indicatorsState.times,
    indicatorsState.selections,
    instanceColors,
    catalogueById,
    chartRef,
    seriesRef,
    colorsRef,
  ]);

  const clear = useCallback(() => {
    indicatorSeriesRef.current.clear();
    ownPanesRef.current.clear();
    levelLinesRef.current.clear();
    markerPluginsRef.current.clear();
    rayPrimitivesRef.current.clear();
    zonePrimitivesRef.current.clear();
    timeProfilePrimitivesRef.current.clear();
  }, []);

  return { clear };
}
