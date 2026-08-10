import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type CandlestickData,
  type HistogramData,
  HistogramSeries,
  type LineData,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPaneApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type Time,
  type TickMarkType,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import { findBar, mergeBar, mergeSeries } from "../data/merge";
import type { IndicatorSource } from "../data/source";
import {
  RESOLUTIONS,
  type Bar,
  type IndicatorCatalogueEntry,
  type IndicatorSelection,
  type Resolution,
} from "../data/types";
import type { MarketDataSource } from "../data/source";
import { formatCrosshairTime, formatInstant, formatTickMark } from "../ui/formatTime";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { candlestickColors, indicatorLineColor, readChartColors, type ChartColors } from "./theme";
import { IndicatorPicker } from "./indicators/IndicatorPicker";
import { type BarsRange, type IndicatorsState, useIndicators } from "./indicators/useIndicators";
import { useIndicatorCatalogue } from "./indicators/useIndicatorCatalogue";
import { useBarFeed, type BarSink } from "./useBarFeed";
import { useOlderBars, type OlderBarsReader } from "./useOlderBars";

export interface ChartProps {
  source: MarketDataSource;
  symbol: string;
  resolution: Resolution;
  onResolutionChange(resolution: Resolution): void;
  /** Rendered at the left of the header — the grid puts its symbol picker
   *  here; a standalone chart passes nothing and just shows the symbol. */
  headerLeft?: React.ReactNode;
  /** Resolutions offered by the selector. Defaults to every one this
   *  terminal knows — a caller that can say which are actually archived for
   *  this symbol (the grid slot) narrows it, so the picker never offers a
   *  resolution that can only end in a refusal (terminal-grid spec, "Slot ma
   *  własny instrument i własny interwał"). */
  resolutions?: readonly Resolution[];
  /** Wskaźniki: the catalogue to build the picker from and the computation
   *  behind it. Omitted, the chart draws candles exactly as before — a caller
   *  with nowhere to compute wskaźniki simply does not offer them. */
  indicatorSource?: IndicatorSource;
  /** What the operator had selected when this chart last mounted — omitted, it
   *  starts with none. Read once, not kept in sync afterward: a caller that
   *  persists selections (the grid slot) restores from here and is notified of
   *  every change via `onIndicatorSelectionsChange`, the same way it owns
   *  `resolution` — but as an initial value rather than a controlled one, since
   *  nothing here needs the reverse (an external reset mid-session). */
  initialIndicatorSelections?: IndicatorSelection[];
  onIndicatorSelectionsChange?(selections: IndicatorSelection[]): void;
}

/** Price-pane overlays and own-pane oscillators both draw today — only the
 *  three later output shapes (markers, zones, levels) do not yet have a
 *  primitive to draw with (E2-E4). Kept as a predicate rather than a filter on
 *  the catalogue itself: the picker still lists every wskaźnik the archive
 *  offers, this only decides which of them the operator may currently pick. */
function canDrawIndicator(entry: IndicatorCatalogueEntry): boolean {
  return (entry.render.pane === "price" || entry.render.pane === "own") && entry.output === "lines";
}

/** The price pane's own stretch factor, set once at chart creation so an
 *  own-pane oscillator added later does not grow to the price chart's own
 *  height — `lightweight-charts`' default (equal stretch for every pane) reads
 *  as "RSI is as important as the candles" the moment a second pane exists. */
const PRICE_PANE_STRETCH = 4;
const OWN_PANE_STRETCH = 1;

function toCandlestick(bar: Bar): CandlestickData<Time> {
  return {
    time: bar.time as UTCTimestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
}

interface Readout {
  bar: Bar;
  /** True when this is the hovered bar rather than the latest one. */
  hovered: boolean;
}

/** How few candles may be left to the viewport's left before older ones are
 *  fetched, counted in bars. It is both the trigger and the target: the pager
 *  keeps going until the viewport has at least this much history behind it, so
 *  one drag to the edge is answered with a screenful rather than a page. */
const OLDER_MARGIN_BARS = 50;

/**
 * One candlestick chart, defined entirely by `symbol` + `resolution` — the same
 * component standalone and inside a grid slot (terminal-chart spec, "Wykres
 * jest sterowany symbolem i rozdzielczością").
 *
 * The chart instance is created once and written to imperatively; bars never
 * pass through React state. See design.md, "Wykres pisze do canvasu, nie do
 * stanu Reacta".
 */
export function Chart({
  source,
  symbol,
  resolution,
  onResolutionChange,
  headerLeft,
  resolutions = RESOLUTIONS,
  indicatorSource,
  initialIndicatorSelections,
  onIndicatorSelectionsChange,
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barsRef = useRef<Bar[]>([]);
  // The pan handler is attached once, with the chart; the pager it calls is
  // recreated whenever symbol, resolution or source change.
  const requestOlderRef = useRef<() => void>(() => {});
  // The current price, drawn as a line with its own axis label — see
  // `syncPriceLine` for why the series' built-in one does not do.
  const priceLineRef = useRef<IPriceLine | null>(null);
  const colorsRef = useRef<ChartColors | null>(null);
  // One series per (wskaźnik, params, line key) — Line unless the line asks for
  // a histogram (MACD's, so far) — see the sync effect below.
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<"Line"> | ISeriesApi<"Histogram">>>(
    new Map(),
  );
  // One pane per (wskaźnik, params) whose `render.pane` is "own" — RSI and MACD
  // each get their own row, the way every other charting platform draws them,
  // rather than sharing one oscillator pane between wskaźniki that disagree
  // about scale.
  const ownPanesRef = useRef<Map<string, IPaneApi<Time>>>(new Map());
  // The catalogue's reference-level hint (RSI's 30/70, …) drawn once per
  // (wskaźnik, params) rather than recomputed every render — the levels never
  // change while the selection is active, only the lines they sit behind do.
  const levelLinesRef = useRef<
    Map<string, { series: ISeriesApi<"Line"> | ISeriesApi<"Histogram">; lines: IPriceLine[] }>
  >(new Map());

  const [readout, setReadout] = useState<Readout | null>(null);
  // The newest bar, mirrored into state on purpose. Reading `barsRef` during
  // render looks cheaper but silently freezes the header: while a candle is
  // forming nothing else about this component's state changes, so React has no
  // reason to re-render and the numbers stop following the market. Coalesced to
  // one write per frame, the same way the crosshair readout is.
  const [latestBar, setLatestBar] = useState<Bar | null>(null);
  const latestFrameRef = useRef(0);

  // --- wskaźniki: chosen by the operator, computed over whatever the chart draws ---
  const [indicatorSelections, setIndicatorSelectionsState] = useState<IndicatorSelection[]>(
    () => initialIndicatorSelections ?? [],
  );
  // A ref, not a dependency: notifying the caller must not itself be a reason
  // to redo anything below, only a side effect of the operator's own action.
  const onIndicatorSelectionsChangeRef = useRef(onIndicatorSelectionsChange);
  onIndicatorSelectionsChangeRef.current = onIndicatorSelectionsChange;
  const setIndicatorSelections = useCallback((next: IndicatorSelection[]) => {
    setIndicatorSelectionsState(next);
    onIndicatorSelectionsChangeRef.current?.(next);
  }, []);
  // The range wskaźniki are computed over — set from what `redraw` actually drew, not
  // from every live tick, so a wskaźnik does not refetch on each forming-candle update
  // (design.md's "na żywo" is a later etap; see `useIndicators`).
  const [barsRange, setBarsRange] = useState<BarsRange | null>(null);

  const catalogue = useIndicatorCatalogue(indicatorSource);
  const catalogueById = useMemo(
    () => new Map(catalogue.entries.map((entry) => [entry.id, entry] as const)),
    [catalogue.entries],
  );
  // A selection restored from a saved slot may name a wskaźnik the catalogue no
  // longer offers (a removed entry, or storage from a build that had a
  // different one). Dropped from what actually computes and draws — surfaced
  // in the header instead — but never rewritten in the caller's storage on its
  // own: only an explicit change through the picker does that (terminal-grid
  // spec, "wpis nieznany katalogowi pomijany z komunikatem"). Skipped entirely
  // while the catalogue is still loading or failed to load, so a slow or
  // flaky read never reads as "the archive removed everything".
  const { knownIndicatorSelections, unknownIndicatorIds } = useMemo(() => {
    if (catalogue.status !== "ready") {
      return { knownIndicatorSelections: indicatorSelections, unknownIndicatorIds: [] as string[] };
    }
    const known: IndicatorSelection[] = [];
    const unknown: string[] = [];
    for (const selection of indicatorSelections) {
      if (catalogueById.has(selection.id)) known.push(selection);
      else unknown.push(selection.id);
    }
    return { knownIndicatorSelections: known, unknownIndicatorIds: unknown };
  }, [indicatorSelections, catalogue.status, catalogueById]);

  const indicatorsState = useIndicators(
    indicatorSource,
    symbol,
    resolution,
    knownIndicatorSelections,
    barsRange,
  );

  // --- the chart instance itself: created once, never on data change ---
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
    // here: the pager keeps asking until `needsMore` below says the margin is
    // filled, which is what stops it looping on its own frame correction.
    const onRangeChange = (range: LogicalRange | null) => {
      if (range && range.from < OLDER_MARGIN_BARS) requestOlderRef.current();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        chart.resize(width, height);
      }
    });
    observer.observe(container);

    const indicatorSeries = indicatorSeriesRef.current;
    const ownPanes = ownPanesRef.current;
    const levelLines = levelLinesRef.current;
    return () => {
      observer.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      // The line belonged to the series that just went away with the chart.
      priceLineRef.current = null;
      // Every wskaźnik series, pane and reference level belonged to it too —
      // `chart.remove()` already freed them, this only stops the sync effect
      // below from reaching for one that is gone.
      indicatorSeries.clear();
      ownPanes.clear();
      levelLines.clear();
    };
  }, []);

  const publishLatestBar = useCallback(() => {
    if (latestFrameRef.current) return;
    latestFrameRef.current = requestAnimationFrame(() => {
      latestFrameRef.current = 0;
      setLatestBar(barsRef.current.at(-1) ?? null);
    });
  }, []);

  useEffect(
    () => () => {
      if (latestFrameRef.current) cancelAnimationFrame(latestFrameRef.current);
    },
    [],
  );

  /**
   * The right-hand scale says what the market is doing now, not what it was doing at the
   * left edge of the viewport.
   *
   * The library's own last-value label reads the last *visible* bar, so a chart panned
   * back a week labelled the scale with a week-old price — the one number on screen an
   * operator is most likely to act on. A price line of our own carries the newest close
   * instead, and follows it as the candle forms.
   */
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    if (!latestBar) {
      if (priceLineRef.current) {
        series.removePriceLine(priceLineRef.current);
        priceLineRef.current = null;
      }
      return;
    }

    const colors = colorsRef.current ?? readChartColors();
    const rising = latestBar.close >= latestBar.open;
    const options = {
      price: latestBar.close,
      color: rising ? colors.up : colors.down,
      lineWidth: 1 as const,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      axisLabelColor: rising ? colors.up : colors.down,
      axisLabelTextColor: colors.surface,
      title: "",
    };

    if (priceLineRef.current) priceLineRef.current.applyOptions(options);
    else priceLineRef.current = series.createPriceLine(options);
  }, [latestBar]);

  // --- crosshair readout, coalesced to one state write per frame ---
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    let frame = 0;
    let pending: MouseEventParams<Time> | null = null;

    const flush = () => {
      frame = 0;
      const param = pending;
      pending = null;
      if (!param?.time) {
        setReadout(null);
        return;
      }
      const bar = findBar(barsRef.current, param.time as number);
      setReadout(bar ? { bar, hovered: true } : null);
    };

    const handler = (param: MouseEventParams<Time>) => {
      pending = param;
      // ~5 quotes a second per pair and a pointer that fires far faster than
      // that: without this, every mouse move is a React render.
      frame ||= requestAnimationFrame(flush);
    };

    chart.subscribeCrosshairMove(handler);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      chart.unsubscribeCrosshairMove(handler);
    };
  }, []);

  /**
   * Redraw the whole series, keeping the operator looking at the same candles.
   *
   * `setData` keeps the visible *logical* range, and logical indices count from the
   * start of the data — so every bar merged in at the front slides the frame that many
   * candles to the right. Shifting the range back by exactly that many puts it back.
   * `previousFirstTime` undefined means nothing was drawn yet, and that is the one case
   * where the frame should move: fit the new series.
   */
  const redraw = useCallback((merged: Bar[], previousFirstTime: number | undefined) => {
    const timeScale = chartRef.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange() ?? null;

    seriesRef.current?.setData(merged.map(toCandlestick));
    // Structural change to what is drawn — recompute wskaźniki over the new span.
    // Not on every live tick: `applyBar`'s hot path never calls `redraw`.
    setBarsRange(merged.length > 0 ? { from: merged[0].time, to: merged.at(-1)!.time } : null);

    if (previousFirstTime === undefined) {
      timeScale?.fitContent();
      return;
    }
    const prepended = merged.findIndex((candidate) => candidate.time === previousFirstTime);
    if (range && prepended > 0) {
      timeScale?.setVisibleLogicalRange({
        from: range.from + prepended,
        to: range.to + prepended,
      });
    }
  }, []);

  // --- the feed writes straight into the series ---
  const applyHistory = useCallback(
    (bars: Bar[]) => {
      // The subscription opens before the history read finishes, so live bars
      // routinely land first — the gateway sends a forming candle within a
      // second, while a deep read takes far longer. Merging (rather than
      // replacing) keeps those bars instead of blanking them until the next
      // tick, which at DAY resolution could be hours away.
      //
      // A reconnect's snapshot comes through here too, which is why the frame
      // is only fitted on the first draw: a chart panned back three thousand
      // candles must not be thrown to the right-hand edge because the socket
      // blinked.
      const previousFirstTime = barsRef.current[0]?.time;
      const merged = mergeSeries(bars, barsRef.current);
      barsRef.current = merged;
      redraw(merged, previousFirstTime);
      setLatestBar(merged.at(-1) ?? null);
      setReadout(null);
    },
    [redraw],
  );

  /** A page of candles older than everything drawn. Merged rather than
   *  concatenated: the archive answers a range, and a range that happens to
   *  end on a bar already drawn must not produce it twice. */
  const applyOlder = useCallback(
    (bars: Bar[]) => {
      const previousFirstTime = barsRef.current[0]?.time;
      const merged = mergeSeries(barsRef.current, bars);
      barsRef.current = merged;
      redraw(merged, previousFirstTime);
    },
    [redraw],
  );

  const applyBar = useCallback((bar: Bar) => {
    const previous = barsRef.current;
    const last = previous.at(-1);
    barsRef.current = mergeBar(previous, bar);

    if (!last || bar.time >= last.time) {
      // The hot path: replace the forming bar, or open a new one.
      seriesRef.current?.update(toCandlestick(bar));
    } else {
      // Older than what is drawn — a reconnect's gap fill. `update()` rejects
      // going backwards, so the merged series is redrawn wholesale. Rare by
      // construction: only after a dropped stream. Through `redraw`, because
      // such a bar can land in front of the series and shift every logical
      // index by one, which without the correction nudges the frame.
      redraw(barsRef.current, previous[0]?.time);
    }
    publishLatestBar();
  }, [publishLatestBar, redraw]);

  const sink: BarSink = useMemo(
    () => ({ onHistory: applyHistory, onBar: applyBar }),
    [applyHistory, applyBar],
  );

  const olderReader: OlderBarsReader = useMemo(
    () => ({
      readSeries: () => barsRef.current,
      deliver: applyOlder,
      needsMore: () => {
        const range = chartRef.current?.timeScale().getVisibleLogicalRange();
        return range ? range.from < OLDER_MARGIN_BARS : false;
      },
    }),
    [applyOlder],
  );

  // Changing symbol, resolution *or source* must not leave the previous
  // series on screen while the new history loads. Source matters as much as
  // the other two: switching mock → gateway was observed showing mock prices
  // under a "gateway" label for the seconds a deep read takes, which is not a
  // stale chart but a wrong one.
  useEffect(() => {
    barsRef.current = [];
    seriesRef.current?.setData([]);
    setReadout(null);
    setLatestBar(null);
    // A wskaźnik computed for the previous series has no business staying on screen
    // while the new one loads — `barsRange` going null empties `indicatorsState.results`
    // (`useIndicators`), which the sync effect below reads as "remove every line".
    setBarsRange(null);
  }, [source, symbol, resolution]);

  // --- wskaźniki: one Line series per (id, params, line key), synced to what the
  // archive last answered. A price-pane entry draws on the candles' own pane; an
  // own-pane entry (RSI, ATR, MACD, …) gets a pane of its own, one per (id,
  // params) rather than one shared by every oscillator — see `canDrawIndicator`.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const colors = colorsRef.current ?? readChartColors();

    const active = new Set<string>();
    const activeOwnPanes = new Set<string>();
    const activeResults = new Set<string>();
    let colorIndex = 0;

    for (const result of indicatorsState.results) {
      const entry = catalogueById.get(result.id);
      if (!entry || !result.lines || !canDrawIndicator(entry)) continue;

      const paramsKey = entry.params.map((p) => result.params[p.name]).join(",");
      const ownPaneKey = `${result.id}|${paramsKey}`;
      activeResults.add(ownPaneKey);

      let paneIndex: number | undefined;
      if (entry.render.pane === "own") {
        activeOwnPanes.add(ownPaneKey);
        let pane = ownPanesRef.current.get(ownPaneKey);
        if (!pane) {
          // `preserveEmptyPane: true` — without it, the chart removes a pane
          // on its own the moment its last series does (`IPaneApi.
          // preserveEmptyPane` docs), racing the explicit `chart.removePane`
          // below: deselecting one of two own-pane wskaźniki left the other's
          // pane index stale and threw. This keeps removal singly-owned, by
          // the cleanup loop, which already knows to look up a live index.
          pane = chart.addPane(true);
          pane.setStretchFactor(OWN_PANE_STRETCH);
          ownPanesRef.current.set(ownPaneKey, pane);
        }
        paneIndex = pane.paneIndex();
      }

      let firstLine: ISeriesApi<"Line"> | ISeriesApi<"Histogram"> | undefined;

      for (const lineSpec of entry.lines) {
        const key = `${result.id}|${paramsKey}|${lineSpec.key}`;
        active.add(key);
        const values = result.lines[lineSpec.key] ?? [];
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
                color: indicatorLineColor(colors, colorIndex),
                lineWidth: 1,
                lastValueVisible: false,
                priceLineVisible: false,
                ...(entry.render.autoscale ? {} : { autoscaleInfoProvider: () => null }),
              },
              paneIndex,
            );
            indicatorSeriesRef.current.set(key, series);
          }
          series.setData(points);
        }
        firstLine ??= series;
        colorIndex++;
      }

      // Reference levels (RSI's 30/70, …) — drawn once per (id, params) on
      // whichever line happens to be first, since every line an entry declares
      // shares that pane's one price scale.
      if (entry.render.levels.length > 0 && firstLine && !levelLinesRef.current.has(ownPaneKey)) {
        const priceLines = entry.render.levels.map((level) =>
          firstLine.createPriceLine({
            price: level,
            color: colors.inkMuted,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "",
          }),
        );
        levelLinesRef.current.set(ownPaneKey, { series: firstLine, lines: priceLines });
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
  }, [indicatorsState.results, indicatorsState.times, catalogueById]);

  const feed = useBarFeed(source, symbol, resolution, sink);
  const older = useOlderBars(source, symbol, resolution, olderReader);
  requestOlderRef.current = older.requestOlder;

  const shown: Readout | null =
    readout ?? (latestBar ? { bar: latestBar, hovered: false } : null);

  const staleStream = feed.streamState === "reconnecting" || feed.streamState === "closed";
  const unsettledIndicators = indicatorsState.results.filter((r) => !r.settled);

  return (
    <section className="flex h-full min-h-0 flex-col bg-panel">
      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-2 py-1.5">
        {headerLeft ?? <span className="text-sm font-semibold text-ink">{symbol}</span>}

        <select
          aria-label="Resolution"
          value={resolution}
          onChange={(e) => onResolutionChange(e.target.value as Resolution)}
          className="rounded border border-border bg-panel-strong px-1.5 py-0.5 text-xs text-ink"
        >
          {resolutions.map((r) => (
            <option key={r} value={r}>
              {RESOLUTION_LABEL[r]}
            </option>
          ))}
        </select>

        {shown && <OhlcReadout bar={shown.bar} indicators={activeIndicatorReadout(shown, indicatorsState, catalogueById)} />}

        <div className="ml-auto flex items-center gap-2">
          {indicatorSource && (
            <IndicatorPicker
              entries={catalogue.entries}
              selections={knownIndicatorSelections}
              onChange={(next) => {
                // An unknown selection is never touched by an edit to a known
                // one — only a change that names it (impossible: it has no
                // checkbox) or a later catalogue read that recognizes it again
                // moves it out of this list.
                const stillUnknown = indicatorSelections.filter((s) => !catalogueById.has(s.id));
                setIndicatorSelections([...stillUnknown, ...next]);
              }}
              canDraw={canDrawIndicator}
            />
          )}
          {unknownIndicatorIds.length > 0 && (
            <span
              title={`No longer offered by the indicator catalogue: ${unknownIndicatorIds.join(", ")}`}
              className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
            >
              {unknownIndicatorIds.length} saved {unknownIndicatorIds.length === 1 ? "indicator" : "indicators"}{" "}
              unavailable
            </span>
          )}
          {unsettledIndicators.length > 0 && (
            <span
              title="The archive did not hold enough history before this range for every value to be trusted yet."
              className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
            >
              warming up
            </span>
          )}
          {indicatorsState.status === "error" && (
            <span className="flex items-center gap-1">
              <span
                title={indicatorsState.error ?? undefined}
                className="rounded border border-critical/40 px-1.5 py-0.5 text-[10px] tracking-wide text-critical uppercase"
              >
                indicators unavailable
              </span>
              <button
                type="button"
                onClick={indicatorsState.retry}
                className="rounded border border-border px-1.5 py-0.5 text-[10px] text-ink hover:bg-panel-strong"
              >
                Retry
              </button>
            </span>
          )}
          <OlderHistoryState older={older} />
          {staleStream && (
            <span className="rounded border border-down/40 px-1.5 py-0.5 text-[10px] tracking-wide text-down uppercase">
              {feed.streamState === "closed" ? "stream closed" : "reconnecting"}
            </span>
          )}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} className="absolute inset-0" data-testid="chart-canvas" />
        <FeedOverlay feed={feed} symbol={symbol} resolution={resolution} />
      </div>
    </section>
  );
}

/**
 * What paging back through the archive is doing, said in the header rather than over the
 * candles: a chart that is dragging in older history is still a chart worth reading, and
 * a failed page must not hide the series that did arrive (terminal-chart spec, "Wykres
 * mówi, co się dzieje ze starszą historią").
 */
function OlderHistoryState({ older }: { older: ReturnType<typeof useOlderBars> }) {
  if (older.status === "loading") {
    return (
      <span className="rounded border border-border px-1.5 py-0.5 text-[10px] tracking-wide text-ink-muted uppercase">
        loading older…
      </span>
    );
  }

  if (older.status === "exhausted") {
    return (
      <span
        title="The archive has nothing older for this pair and resolution."
        className="rounded border border-border px-1.5 py-0.5 text-[10px] tracking-wide text-ink-muted uppercase"
      >
        start of history
      </span>
    );
  }

  if (older.status === "error") {
    return (
      <span className="flex items-center gap-1">
        <span
          title={older.error ?? undefined}
          className="rounded border border-critical/40 px-1.5 py-0.5 text-[10px] tracking-wide text-critical uppercase"
        >
          older history failed
        </span>
        <button
          type="button"
          onClick={older.retry}
          className="rounded border border-border px-1.5 py-0.5 text-[10px] text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </span>
    );
  }

  return null;
}

interface IndicatorReadoutEntry {
  key: string;
  label: string;
  value: number | null;
}

/**
 * The wskaźnik values for whichever bar `OhlcReadout` is already showing — the same
 * bar the OHLC fields answer for, found by matching time rather than index, since a
 * wskaźnik's own axis can start later than the candle series (`warmup_from`).
 */
function activeIndicatorReadout(
  shown: Readout,
  indicatorsState: IndicatorsState,
  catalogueById: Map<string, IndicatorCatalogueEntry>,
): IndicatorReadoutEntry[] {
  const index = indicatorsState.times.indexOf(shown.bar.time);
  if (index === -1) return [];

  const entries: IndicatorReadoutEntry[] = [];
  for (const result of indicatorsState.results) {
    const entry = catalogueById.get(result.id);
    if (!entry || !result.lines) continue;
    for (const lineSpec of entry.lines) {
      entries.push({
        key: `${result.id}|${lineSpec.key}`,
        label: fillLabelTemplate(lineSpec.label, result.params),
        value: result.lines[lineSpec.key]?.[index] ?? null,
      });
    }
  }
  return entries;
}

function fillLabelTemplate(template: string, params: Record<string, number>): string {
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

function OhlcReadout({ bar, indicators }: { bar: Bar; indicators: IndicatorReadoutEntry[] }) {
  return (
    <span className="flex flex-wrap items-center gap-2 text-xs text-ink-secondary">
      <Field label="O" value={bar.open} />
      <Field label="H" value={bar.high} />
      <Field label="L" value={bar.low} />
      <Field label="C" value={bar.close} />
      <time className="text-ink-muted">{formatInstant(bar.time)}</time>
      {indicators.map((entry) => (
        <span key={entry.key} className="text-ink-muted">
          {entry.label}{" "}
          <span className="text-ink">{entry.value === null ? "…" : entry.value}</span>
        </span>
      ))}
    </span>
  );
}

function Field({ label, value }: { label: string; value: number }) {
  return (
    <span className="text-ink-muted">
      {label} <span className="text-ink">{value}</span>
    </span>
  );
}

function FeedOverlay({
  feed,
  symbol,
  resolution,
}: {
  feed: ReturnType<typeof useBarFeed>;
  symbol: string;
  resolution: Resolution;
}) {
  if (feed.status === "loading") {
    return (
      <Veil>
        <span className="text-sm text-ink-muted">Loading {symbol} history…</span>
      </Veil>
    );
  }

  if (feed.status === "empty") {
    return (
      <Veil>
        <span className="text-sm text-ink-muted">
          No candles for {symbol} at {RESOLUTION_LABEL[resolution]}.
        </span>
      </Veil>
    );
  }

  if (feed.status === "error") {
    return (
      <Veil>
        <div className="text-center">
          <p className="text-sm text-critical">Could not load {symbol}.</p>
          <p className="mt-1 max-w-xs text-xs text-ink-muted">{feed.error}</p>
          <button
            type="button"
            onClick={feed.retry}
            className="mt-3 rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
          >
            Retry
          </button>
        </div>
      </Veil>
    );
  }

  return null;
}

/**
 * Everything the chart has to say when it cannot draw: loading, empty, refused.
 *
 * `z-10` is load-bearing. Lightweight-charts mounts its canvases at `z-index` 1 and 2 in
 * a container that opens no stacking context, so they compete with this overlay
 * directly. At the default level the veil loses, and every message renders into the DOM,
 * passes its test, and is painted over by an empty canvas.
 */
function Veil({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-panel/80">
      {children}
    </div>
  );
}
