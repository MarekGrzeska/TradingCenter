import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { findBar, mergeBar, mergeSeries } from "../data/merge";
import { RESOLUTIONS, type Bar, type Resolution } from "../data/types";
import type { MarketDataSource } from "../data/source";
import { candlestickColors, readChartColors } from "./theme";
import { useBarFeed, type BarSink } from "./useBarFeed";

export interface ChartProps {
  source: MarketDataSource;
  symbol: string;
  resolution: Resolution;
  onResolutionChange(resolution: Resolution): void;
  /** Rendered at the left of the header — the grid puts its symbol picker
   *  here; a standalone chart passes nothing and just shows the symbol. */
  headerLeft?: React.ReactNode;
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
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barsRef = useRef<Bar[]>([]);

  const [readout, setReadout] = useState<Readout | null>(null);
  const [lastIsForming, setLastIsForming] = useState(false);

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
      timeScale: { borderColor: colors.axis, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: false,
      width: container.clientWidth,
      height: container.clientHeight,
    });
    const series = chart.addSeries(CandlestickSeries, candlestickColors(colors));

    chartRef.current = chart;
    seriesRef.current = series;

    // Whatever the feed already delivered before this effect re-ran (a
    // StrictMode remount, most often) is redrawn rather than lost.
    if (barsRef.current.length > 0) {
      series.setData(barsRef.current.map(toCandlestick));
      chart.timeScale().fitContent();
    }

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        chart.resize(width, height);
      }
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

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

  // --- the feed writes straight into the series ---
  const applyHistory = useCallback((bars: Bar[]) => {
    // The subscription opens before the history read finishes, so live bars
    // routinely land first — the gateway sends a forming candle within a
    // second, while a deep read takes far longer. Merging (rather than
    // replacing) keeps those bars instead of blanking them until the next
    // tick, which at DAY resolution could be hours away.
    const merged = mergeSeries(bars, barsRef.current);
    barsRef.current = merged;
    seriesRef.current?.setData(merged.map(toCandlestick));
    chartRef.current?.timeScale().fitContent();
    setLastIsForming(merged.at(-1)?.forming ?? false);
    setReadout(null);
  }, []);

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
      // construction: only after a dropped stream.
      seriesRef.current?.setData(barsRef.current.map(toCandlestick));
    }
    setLastIsForming(barsRef.current.at(-1)?.forming ?? false);
  }, []);

  const sink: BarSink = useMemo(
    () => ({ onHistory: applyHistory, onBar: applyBar }),
    [applyHistory, applyBar],
  );

  // A symbol or resolution change must not leave the previous instrument's
  // candles on screen while the new history loads.
  useEffect(() => {
    barsRef.current = [];
    seriesRef.current?.setData([]);
    setReadout(null);
    setLastIsForming(false);
  }, [symbol, resolution]);

  const feed = useBarFeed(source, symbol, resolution, sink);

  const shown: Readout | null =
    readout ??
    (barsRef.current.length > 0
      ? { bar: barsRef.current[barsRef.current.length - 1], hovered: false }
      : null);

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
          {RESOLUTIONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        {shown && <OhlcReadout bar={shown.bar} />}

        <div className="ml-auto flex items-center gap-2">
          {lastIsForming && !shown?.hovered && (
            <span
              title="This candle is still being built from quotes and will change."
              className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
            >
              forming
            </span>
          )}
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

function OhlcReadout({ bar }: { bar: Bar }) {
  return (
    <span className="flex items-center gap-2 text-xs text-ink-secondary">
      <Field label="O" value={bar.open} />
      <Field label="H" value={bar.high} />
      <Field label="L" value={bar.low} />
      <Field label="C" value={bar.close} />
      <span className="text-ink-muted">
        V{" "}
        {bar.volume === null ? (
          // Not zero — the stream simply doesn't carry volume (see the
          // gateway README). Saying "0" would be a claim about the market.
          <span title="This source does not report volume for live candles.">n/a</span>
        ) : (
          <span className="text-ink">{bar.volume}</span>
        )}
      </span>
      <time className="text-ink-muted">{new Date(bar.time * 1000).toISOString().slice(0, 16).replace("T", " ")}</time>
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
          No candles for {symbol} at {resolution}.
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

function Veil({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-panel/80">{children}</div>
  );
}
