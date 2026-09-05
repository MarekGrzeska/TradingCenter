import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import type { AgentChartDrawing, AgentDrawingPatch } from "../agent/agentApi";
import type { DrawingsStatus } from "../agent/drawingsStore";
import { findBar, mergeBar, mergeSeries } from "../data/merge";
import type { IndicatorSource } from "../data/source";
import {
  RESOLUTIONS,
  type Bar,
  type ChartFocusRequest,
  type IndicatorSelection,
  type Resolution,
  type VisibleTimeRange,
} from "../data/types";
import type { MarketDataSource } from "../data/source";
import { readChartColors, type ChartColors } from "./theme";
import { DrawingCard } from "./DrawingCard";
import {
  MAX_VISIBLE_BARS,
  MIN_VISIBLE_BARS,
  OLDER_MARGIN_BARS,
  RESOLUTION_SECONDS,
  RIGHT_EDGE_SLACK_BARS,
  nearestBarIndex,
  reachesBack,
  toCandlestick,
  type PendingResolutionFrame,
} from "./chartWindow";
import { FeedOverlay, OhlcReadout } from "./ChartReadout";
import { activeIndicatorReadout, type Readout } from "./indicatorReadout";
import { useChartInstance } from "./useChartInstance";
import { useDrawingLayers } from "./useDrawingLayers";
import { useIndicatorLayers } from "./useIndicatorLayers";
import { useChartIndicators } from "./useChartIndicators";
import { useChartFocus } from "./useChartFocus";
import { ChartHeader } from "./ChartHeader";
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
  /** Resolutions offered by the selector. Defaults to every one this terminal knows; a caller that can say
   *  which are archived for this symbol narrows it, so the picker never offers a certain refusal. */
  resolutions?: readonly Resolution[];
  /** Indicators: the catalogue to build the picker from and the computation
   *  behind it. Omitted, the chart draws candles exactly as before — a caller
   *  with nowhere to compute indicators simply does not offer them. */
  indicatorSource?: IndicatorSource;
  /** What the operator had selected when this chart last mounted. Read once, not kept in sync: a caller
   *  that persists selections restores from here and is notified of every change afterwards. */
  initialIndicatorSelections?: IndicatorSelection[];
  onIndicatorSelectionsChange?(selections: IndicatorSelection[]): void;
  /** A one-off "show this fragment of the axis". A new object is what triggers a pursuit; the same
   *  reference twice is a no-op, which lets the caller pass its stored value on every render. */
  focusRequest?: ChartFocusRequest | null;
  /** Called once `focusRequest` has been either applied or given up on — never both, and
   *  never left uncalled for a request the chart accepted. The caller's cue to stop
   *  offering it again (`terminal-chart` spec, "Kadr MUST być żądaniem jednorazowym"). */
  onFocusRequestSettled?(): void;
  /** Fired whenever the visible span changes, and with `null` when there is nothing to report. Never read
   *  back here: it exists for a caller keeping its own record of what the operator is looking at. */
  onVisibleRangeChange?(range: VisibleTimeRange | null): void;
  /** Objects drawn on this instrument, together with the operator's own hand on them. Not indicators and
   *  not on the same lifecycle: they survive a resolution change, because they belong to the instrument. */
  drawings?: ChartDrawings;
}

/** What the chart needs to draw the objects on an instrument and let the operator manage them. `remove`
 *  and `patch` answer null on success and the sentence to show on failure — the list keeps what it had. */
export interface ChartDrawings {
  items: readonly AgentChartDrawing[];
  status: DrawingsStatus;
  error: string | null;
  remove(id: number): Promise<string | null>;
  patch(id: number, patch: AgentDrawingPatch): Promise<string | null>;
}

/** One shared empty array for a chart with no drawings, so "none" is the same reference
 *  on every render and never restarts the sync effect that watches it. */
const EMPTY_DRAWINGS: readonly AgentChartDrawing[] = [];
/**
 * One candlestick chart, defined entirely by `symbol` + `resolution`. The instance is created once and
 * written to imperatively; bars never pass through React state.
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
  focusRequest = null,
  onFocusRequestSettled,
  onVisibleRangeChange,
  drawings,
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barsRef = useRef<Bar[]>([]);
  // The pan handler is attached once, with the chart; the pager it calls is
  // recreated whenever symbol, resolution or source change.
  const requestOlderRef = useRef<() => void>(() => {});
  // The pager's other door: one read straight to a named moment, for a focus that would
  // otherwise be walked to a page at a time (`useOlderBars`, `reachBack`).
  const reachBackRef = useRef<(target: number) => void>(() => {});
  // The current price, drawn as a line with its own axis label — see
  // `syncPriceLine` for why the series' built-in one does not do.
  const priceLineRef = useRef<IPriceLine | null>(null);
  const colorsRef = useRef<ChartColors | null>(null);

  // The array alone, not the whole prop: a caller that rebuilds the object every render
  // (the grid slot does) must not make the sync effect below run every render with it.
  const allObjects = drawings?.items ?? EMPTY_DRAWINGS;
  // What the chart draws, against what the instrument carries — two different questions. A hidden object
  // is as absent from the canvas as one removed; the list below gets them all, being the only way back.
  const drawnObjects = useMemo(
    () => (allObjects.some((drawing) => drawing.hidden) ? allObjects.filter((d) => !d.hidden) : allObjects),
    [allObjects],
  );

  // State of the *screen*, and of this slot's screen alone — not of the instrument. Two slots showing
  // US100 show the same objects, and the operator points at one of them in one of the slots.
  const [selected, setSelected] = useState<{ id: number; at: { x: number; y: number } | null } | null>(
    null,
  );
  const selectedId = selected?.id ?? null;
  // From the whole list, not from what is drawn: hiding the picked object leaves its card open with the
  // button flipped, because the nearest way to undo has to be where the action happened.
  const selectedDrawing = allObjects.find((drawing) => drawing.id === selectedId) ?? null;

  // The objects of the previous instrument are not on the chart any more, so nothing of theirs can be
  // picked out.
  useEffect(() => {
    setSelected(null);
  }, [symbol]);

  // An object removed while picked takes the selection with it: what is not there cannot be pointed at.
  // Hiding is deliberately not that — the object is still on the instrument.
  useEffect(() => {
    setSelected((current) =>
      current === null || allObjects.some((drawing) => drawing.id === current.id) ? current : null,
    );
  }, [allObjects]);

  useEffect(() => {
    if (selectedId === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
    };
    // On the document rather than on the chart's own element: `Escape` has to reach the selection wherever
    // the focus happens to be.
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [selectedId]);

  const [readout, setReadout] = useState<Readout | null>(null);
  // The newest bar, mirrored into state on purpose. Reading the ref during render looks cheaper and
  // silently freezes the header, because nothing else about this component's state changes.
  const [latestBar, setLatestBar] = useState<Bar | null>(null);
  const latestFrameRef = useRef(0);

  // Everything from the picker to the numbers behind a line lives in `useChartIndicators`, called here
  // because effects run in declaration order and its window sync must exist before the chart instance.
  const indicators = useChartIndicators({
    indicatorSource,
    symbol,
    resolution,
    initialIndicatorSelections,
    onIndicatorSelectionsChange,
    chartRef,
    barsRef,
    colorsRef,
  });
  // The header takes the hook's return whole; what the chart itself needs from it is
  // these five, all of them for drawing rather than for rendering.
  const { indicatorsState, catalogueById, instanceColors, readoutAssignment } = indicators;
  const { syncIndicatorWindowRef, holdIndicatorWindow, releaseIndicatorWindow, clearIndicatorWindow } =
    indicators;

  // Declared up here rather than with the rest of the focus refs, because the chart-instance call reads
  // it during render and a ref read during render must already exist.
  const onVisibleRangeChangeRef = useRef(onVisibleRangeChange);
  onVisibleRangeChangeRef.current = onVisibleRangeChange;

  // Declared here, above every hook that draws onto the chart, because effects run in declaration order.
  // `useChartInstance` carries why its one moving part arrives as a ref.
  const clearIndicatorLayersRef = useRef<() => void>(() => {});
  useChartInstance({
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
  });

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
   * The right-hand scale says what the market is doing now. The library's own last-value label reads the
   * last *visible* bar, so a chart panned back a week labelled the scale with a week-old price.
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

  // `hoveredObjectId` is whatever the primitives' own `hitTest` answered on these coordinates, so a click
  // is measured against the geometry the object was drawn with, not a second copy kept in step by hand.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const onClick = (param: MouseEventParams<Time>) => {
      const hovered = param.hoveredObjectId;
      const id = typeof hovered === "string" ? Number(hovered) : NaN;
      // Empty space is an answer, not a missing one: it puts the selection down
      // (`terminal-chart-objects` spec, "Kliknięcie w puste miejsce").
      if (!Number.isFinite(id)) {
        setSelected(null);
        return;
      }
      setSelected({ id, at: param.point ? { x: param.point.x, y: param.point.y } : null });
    };

    chart.subscribeClick(onClick);
    return () => chart.unsubscribeClick(onClick);
  }, []);

  const { pendingFocusRef, pursueFocus, settlePendingFocus, abandonPendingFocus } = useChartFocus({
    symbol,
    resolution,
    focusRequest,
    onFocusRequestSettled,
    chartRef,
    barsRef,
    requestOlderRef,
    reachBackRef,
  });

  const pendingResolutionFrameRef = useRef<PendingResolutionFrame | null>(null);
  const previousParamsRef = useRef({ source, symbol, resolution });

  /**
   * Redraw the whole series, keeping the operator on the same candles: `setData` keeps the visible *logical*
   * range, so every bar merged in at the front slides the frame right. Undefined means nothing was drawn yet.
   */
  const redraw = useCallback((merged: Bar[], previousFirstTime: number | undefined, syncIndicators = true) => {
    const timeScale = chartRef.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange() ?? null;

    seriesRef.current?.setData(merged.map(toCandlestick));

    // Wrapped so the indicator window is pointed at the frame this leaves behind, not the one it found:
    // reading the viewport before that lands would compute indicators for where the chart was.
    const reframe = () => {
    if (previousFirstTime === undefined) {
      // A resolution change leaves a viewport behind for exactly this moment — the series' first draw —
      // to stand over, instead of `fitContent()`'s whole-series view.
      const pendingFrame = pendingResolutionFrameRef.current;
      pendingResolutionFrameRef.current = null;
      if (pendingFrame && merged.length > 0) {
        const periodSeconds = RESOLUTION_SECONDS[resolution];
        const span = Math.round((pendingFrame.to - pendingFrame.from) / periodSeconds);
        const bars = Math.min(MAX_VISIBLE_BARS, Math.max(MIN_VISIBLE_BARS, span));
        let from: number;
        let to: number;
        if (pendingFrame.atRightEdge) {
          to = merged.length - 1;
          from = to - bars + 1;
        } else {
          const centerIndex = nearestBarIndex(merged, (pendingFrame.from + pendingFrame.to) / 2);
          from = centerIndex - Math.floor(bars / 2);
          to = from + bars - 1;
        }
        timeScale?.setVisibleLogicalRange({ from, to });
        return;
      }
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
    };
    reframe();
    // Structural change to what is drawn — recompute, whatever the frame did. Not on every live tick:
    // `applyBar`'s hot path never calls `redraw`. And not per page of older history: the pager says when.
    if (syncIndicators) syncIndicatorWindowRef.current(true);
  }, [resolution, syncIndicatorWindowRef]);

  const applyHistory = useCallback(
    (bars: Bar[]) => {
      // The subscription opens before the history read finishes, so live bars routinely land first. Merging
      // keeps them instead of blanking until the next tick, which at DAY could be hours away.
      const previousFirstTime = barsRef.current[0]?.time;
      const merged = mergeSeries(bars, barsRef.current);
      barsRef.current = merged;
      redraw(merged, previousFirstTime);
      setLatestBar(merged.at(-1) ?? null);
      setReadout(null);
      // The first attempt at a pending focus often finds too short a series to even start the pager —
      // retried here now that the deep read has landed.
      if (pendingFocusRef.current) pursueFocus(pendingFocusRef.current);
    },
    [redraw, pursueFocus, pendingFocusRef],
  );

  /** A page of candles older than everything drawn. Merged rather than
   *  concatenated: the archive answers a range, and a range that happens to
   *  end on a bar already drawn must not produce it twice. */
  const applyOlder = useCallback(
    (bars: Bar[]) => {
      const previousFirstTime = barsRef.current[0]?.time;
      const merged = mergeSeries(barsRef.current, bars);
      barsRef.current = merged;
      holdIndicatorWindow();
      redraw(merged, previousFirstTime, false);

      // Checked here rather than by watching `older.status`: a `"loading"` render is not guaranteed to
      // commit, since React may batch it away with the `"idle"` that follows a fast answer.
      const pending = pendingFocusRef.current;
      if (pending) {
        const reached = reachesBack(merged, pending);
        // The exact condition `useOlderBars` itself uses to call the archive out of history: a page that
        // left the series starting where it started is a page of candles already drawn.
        const noProgress = (merged[0]?.time ?? previousFirstTime) >= (previousFirstTime ?? -Infinity);
        if (reached || noProgress) settlePendingFocus(pending);
      }
    },
    [redraw, settlePendingFocus, pendingFocusRef, holdIndicatorWindow],
  );

  const applyBar = useCallback((bar: Bar) => {
    const previous = barsRef.current;
    const last = previous.at(-1);
    barsRef.current = mergeBar(previous, bar);

    if (!last || bar.time >= last.time) {
      // The hot path: replace the forming bar, or open a new one.
      seriesRef.current?.update(toCandlestick(bar));
      if (last && bar.time > last.time) {
        // `bar` opened a new period, which means `last` just closed. Slide the window to it and let the
        // indicators requery — never on the forming candle moving, which is caught above.
        syncIndicatorWindowRef.current(true);
      }
    } else {
      // Older than what is drawn — a reconnect's gap fill. `update()` rejects going backwards, so the
      // merged series is redrawn wholesale, through `redraw`, because such a bar shifts every logical index.
      redraw(barsRef.current, previous[0]?.time);
    }
    publishLatestBar();
  }, [publishLatestBar, redraw, syncIndicatorWindowRef]);

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
        const viewportNeedsMore = range ? range.from < OLDER_MARGIN_BARS : false;
        const pending = pendingFocusRef.current;
        const focusNeedsMore = pending !== null && !reachesBack(barsRef.current, pending);
        return viewportNeedsMore || focusNeedsMore;
      },
      // The pager gave up before the focus was reachable. Settled here rather than left pending: an
      // unsettled request never tells the caller it is done, and the operator is never told why.
      stoppedShort: () => {
        const pending = pendingFocusRef.current;
        if (pending) settlePendingFocus(pending);
      },
      settled: releaseIndicatorWindow,
    }),
    [applyOlder, settlePendingFocus, pendingFocusRef, releaseIndicatorWindow],
  );

  // Changing symbol, resolution *or source* must not leave the previous series on screen. Source matters
  // as much: switching mock → gateway showed mock prices under a "gateway" label for seconds.
  useEffect(() => {
    // `barsRef` still holds the outgoing series here, so a resolution change — and only that — captures
    // its viewport before the lines below clear it. The comparison needs the previous render's params.
    const previous = previousParamsRef.current;
    previousParamsRef.current = { source, symbol, resolution };
    const onlyResolutionChanged =
      previous.source === source && previous.symbol === symbol && previous.resolution !== resolution;

    if (onlyResolutionChanged) {
      const range = chartRef.current?.timeScale().getVisibleLogicalRange();
      const series = barsRef.current;
      if (range && series.length > 0) {
        const fromIndex = Math.max(0, Math.round(range.from));
        const toIndex = Math.min(series.length - 1, Math.round(range.to));
        const fromTime = series[fromIndex]?.time;
        const toTime = series[toIndex]?.time;
        if (fromTime !== undefined && toTime !== undefined) {
          pendingResolutionFrameRef.current = {
            from: fromTime,
            to: toTime,
            atRightEdge: toIndex >= series.length - 1 - RIGHT_EDGE_SLACK_BARS,
          };
        }
      }
    }

    barsRef.current = [];
    seriesRef.current?.setData([]);
    setReadout(null);
    setLatestBar(null);
    // An indicator computed for the previous series has no business staying on screen while the new one
    // loads — `barsRange` going null empties the results, which the sync effect reads as "remove every line".
    clearIndicatorWindow();
    // The cleanup, not the body: a cleanup runs only when the params are about to change, never on the
    // initial mount — which is what a focus supplied as a starting prop needs.
    return abandonPendingFocus;
  }, [source, symbol, resolution, clearIndicatorWindow, abandonPendingFocus]);

  // Declared here rather than higher up: effects run in declaration order, and this one has to find a
  // chart the instance effect above has already created.
  const { clear: clearIndicatorLayers } = useIndicatorLayers({
    chartRef,
    seriesRef,
    colorsRef,
    indicatorsState,
    catalogueById,
    instanceColors,
  });
  // The other end of the knot the instance hook describes: the ref is filled here, after
  // the hook that owns this function has returned, and read at unmount.
  clearIndicatorLayersRef.current = clearIndicatorLayers;

  // Below the chart instance effect for the same reason the indicator layers are: their
  // effects have to find a chart that has already been created.
  useDrawingLayers({ chartRef, seriesRef, colorsRef, drawnObjects, latestBar, selectedId });

  const feed = useBarFeed(source, symbol, resolution, sink);
  const older = useOlderBars(source, symbol, resolution, olderReader);
  requestOlderRef.current = older.requestOlder;
  reachBackRef.current = older.reachBack;

  /** The rare case `applyOlder`'s own check cannot see: the pager walked every empty window and delivered
   *  nothing, so no page arrived to trigger it. `"exhausted"`/`"error"` are never the initial value. */
  useEffect(() => {
    if (older.status !== "exhausted" && older.status !== "error") return;
    if (pendingFocusRef.current) settlePendingFocus(pendingFocusRef.current);
  }, [older.status, settlePendingFocus, pendingFocusRef]);

  const shown: Readout | null =
    readout ?? (latestBar ? { bar: latestBar, hovered: false } : null);


  return (
    <section className="flex h-full min-h-0 flex-col bg-panel">
      <ChartHeader
        symbol={symbol}
        resolution={resolution}
        resolutions={resolutions}
        onResolutionChange={onResolutionChange}
        headerLeft={headerLeft}
        hasIndicatorSource={indicatorSource !== undefined}
        indicators={indicators}
        drawings={drawings}
        selectedId={selectedId}
        // Picked from the list, so there is no click on the chart to sit beside — the
        // card takes its own corner (`DrawingCard.cardPosition`).
        onSelectDrawing={(id) => setSelected(id === null ? null : { id, at: null })}
        feed={feed}
        older={older}
      />

      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} className="absolute inset-0" data-testid="chart-canvas" />
          {/* The legend sits *on* the chart rather than in the header, and for a reason beyond convention:
              in the header a value changing width mid-pan could re-wrap the row and set the ResizeObserver
              re-laying out the chart in the middle of a drag. */}
        {shown && (
          <div
            data-testid="chart-readout"
            className="pointer-events-none absolute top-1.5 left-2 z-10"
          >
            <OhlcReadout
              bar={shown.bar}
              indicators={activeIndicatorReadout(
                shown,
                indicatorsState.times,
                readoutAssignment.drawn,
                readoutAssignment.lineColors,
                colorsRef.current ?? readChartColors(),
              )}
            />
          </div>
        )}
        {drawings && selectedDrawing && (
          <DrawingCard
            drawing={selectedDrawing}
            drawings={drawings}
            at={selected?.at ?? null}
            onClose={() => setSelected(null)}
          />
        )}
        <FeedOverlay feed={feed} symbol={symbol} resolution={resolution} />
      </div>
    </section>
  );
}
