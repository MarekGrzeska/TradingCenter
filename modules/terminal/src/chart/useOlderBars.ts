import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketDataSource } from "../data/source";
import type { Bar, Resolution } from "../data/types";

export type OlderBarsStatus = "idle" | "loading" | "exhausted" | "error";

export interface OlderBarsReader {
  /** The series as it is drawn right now, oldest first. */
  readSeries(): readonly Bar[];
  /** Bars older than the drawn series, to be merged into it. */
  deliver(bars: Bar[]): void;
}

export interface OlderBars {
  status: OlderBarsStatus;
  error: string | null;
  /** Ask for the page older than what is drawn. Ignored while a page is in
   *  flight, after the archive ran out, and after a failure — a failure waits
   *  for `retry`, so a pan against a dead archive is not a request loop. */
  requestOlder(): void;
  retry(): void;
}

/** How many of the oldest drawn bars define the span asked for. The window is
 *  measured in time the drawn candles actually occupy rather than a period
 *  length per resolution: `types.ts` refuses to keep such a table (a daily
 *  candle starts at the venue's session, not at UTC midnight), and a table
 *  would be blind to weekends besides — 500 minute candles are eight hours of
 *  candles but far more than eight hours of clock. */
const PAGE_BARS = 300;

/** Empty windows walked through before this pair counts as having no more
 *  history. One empty window means nothing: a weekend, a holiday and a pause in
 *  collection all look exactly like a range with no candles in it. The window
 *  doubles each time, so four of them reach back eight times the first. */
const EMPTY_WINDOWS = 4;

/** Floor for the window, for the case where the drawn bars share a timestamp
 *  span of zero — a single settled bar plus a forming one, most often. Without
 *  it the request would be an empty range answered instantly by nothing. */
const MIN_SPAN_SECONDS = 60;

function pageSpan(series: readonly Bar[]): number {
  const oldest = series[0].time;
  const edge = series[Math.min(PAGE_BARS, series.length - 1)].time;
  return Math.max(edge - oldest, MIN_SPAN_SECONDS);
}

/**
 * Older candles, a page at a time, for one (symbol, resolution).
 *
 * This is a range read, which is the thing the hub took away from charts — and it stays
 * taken away for the live edge. Every read here ends at the oldest *drawn* bar, so it can
 * only ever touch periods already settled: the right-hand edge, the forming candle and
 * everything a reconnect fills still come from the subscription's snapshot alone
 * (design.md, "Odczyt zakresu wraca do wykresu, a to on kiedyś tworzył szew").
 */
export function useOlderBars(
  source: MarketDataSource,
  symbol: string,
  resolution: Resolution,
  reader: OlderBarsReader,
): OlderBars {
  const [status, setStatus] = useState<OlderBarsStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  // Recreated on every parent render, like the feed's sink — held in a ref so a
  // re-render never disturbs a read in flight.
  const readerRef = useRef(reader);
  readerRef.current = reader;

  // Read by the load loop, which cannot see React state: the whole point of the
  // guard is to answer *before* the next render.
  const busyRef = useRef(false);
  const blockedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // Each (source, symbol, resolution) gets its own run. The generation makes a
  // late answer from the previous one dead on arrival, the way the feed's
  // `cancelled` flag does.
  const generationRef = useRef(0);

  useEffect(() => {
    generationRef.current += 1;
    busyRef.current = false;
    blockedRef.current = false;
    setStatus("idle");
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, [source, symbol, resolution]);

  const load = useCallback(async () => {
    if (busyRef.current || blockedRef.current) return;

    const series = readerRef.current.readSeries();
    // Two bars are the least that can say how long a page is worth asking for.
    if (series.length < 2) return;

    const generation = generationRef.current;
    // `??=` covers the one call that could beat the effect below to it; every
    // later call gets the controller that effect installed for this pair.
    const controller = (abortRef.current ??= new AbortController());
    busyRef.current = true;
    setStatus("loading");

    let cursor = series[0].time;
    let span = pageSpan(series);

    try {
      for (let window = 0; window < EMPTY_WINDOWS; window++) {
        const bars = await source.history(
          { symbol, resolution, from: cursor - span, to: cursor },
          controller.signal,
        );
        if (generation !== generationRef.current) return;

        if (bars.length > 0) {
          readerRef.current.deliver(bars);
          setStatus("idle");
          return;
        }
        cursor -= span;
        span *= 2;
      }
      blockedRef.current = true;
      setStatus("exhausted");
    } catch (cause: unknown) {
      if (generation !== generationRef.current || controller.signal.aborted) return;
      blockedRef.current = true;
      setError(cause instanceof Error ? cause.message : "could not read older candles");
      setStatus("error");
    } finally {
      if (generation === generationRef.current) busyRef.current = false;
    }
  }, [source, symbol, resolution]);

  const loadRef = useRef(load);
  loadRef.current = load;

  const requestOlder = useCallback(() => {
    void loadRef.current();
  }, []);

  const retry = useCallback(() => {
    // Only a failure is retried. "Exhausted" is an answer, not an outage: the
    // archive said there is nothing older, and asking again would ask the same
    // question of the same data.
    if (status !== "error") return;
    blockedRef.current = false;
    setError(null);
    setStatus("idle");
    void loadRef.current();
  }, [status]);

  return { status, error, requestOlder, retry };
}
