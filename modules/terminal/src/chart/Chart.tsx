import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type CandlestickData,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type Time,
  type TickMarkType,
  type UTCTimestamp,
} from "lightweight-charts";
import { findBar, mergeBar, mergeSeries } from "../data/merge";
import { RESOLUTIONS, type Bar, type Resolution } from "../data/types";
import type { MarketDataSource } from "../data/source";
import { formatCrosshairTime, formatInstant, formatTickMark } from "../ui/formatTime";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { candlestickColors, readChartColors, type ChartColors } from "./theme";
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
}

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

  const [readout, setReadout] = useState<Readout | null>(null);
  // The newest bar, mirrored into state on purpose. Reading `barsRef` during
  // render looks cheaper but silently freezes the header: while a candle is
  // forming nothing else about this component's state changes, so React has no
  // reason to re-render and the numbers stop following the market. Coalesced to
  // one write per frame, the same way the crosshair readout is.
  const [latestBar, setLatestBar] = useState<Bar | null>(null);
  const latestFrameRef = useRef(0);

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

    return () => {
      observer.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      // The line belonged to the series that just went away with the chart.
      priceLineRef.current = null;
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
  }, [source, symbol, resolution]);

  const feed = useBarFeed(source, symbol, resolution, sink);
  const older = useOlderBars(source, symbol, resolution, olderReader);
  requestOlderRef.current = older.requestOlder;

  const shown: Readout | null =
    readout ?? (latestBar ? { bar: latestBar, hovered: false } : null);

  const staleStream = feed.streamState === "reconnecting" || feed.streamState === "closed";

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

        {shown && <OhlcReadout bar={shown.bar} />}

        <div className="ml-auto flex items-center gap-2">
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

function OhlcReadout({ bar }: { bar: Bar }) {
  return (
    <span className="flex items-center gap-2 text-xs text-ink-secondary">
      <Field label="O" value={bar.open} />
      <Field label="H" value={bar.high} />
      <Field label="L" value={bar.low} />
      <Field label="C" value={bar.close} />
      <time className="text-ink-muted">{formatInstant(bar.time)}</time>
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
