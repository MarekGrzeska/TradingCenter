import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketDataSource } from "../data/source";
import type { Bar, Resolution } from "../data/types";

export type OlderBarsStatus = "idle" | "loading" | "exhausted" | "error";

export interface OlderBarsReader {
  /** The series as it is drawn right now, oldest first. */
  readSeries(): readonly Bar[];
  /** Bars older than the drawn series, to be merged into it. */
  deliver(bars: Bar[]): void;
  /** True while the viewport still has too few candles to its left. The pager
   *  keeps fetching until this goes false, so one drag to the edge is answered
   *  with as much history as the screen needs — not with one page per drag. */
  needsMore(): boolean;
  /** `MAX_PAGES` ran out before the caller's appetite did. Distinct from `"exhausted"` on purpose:
   *  a run that gave up ends in `"idle"` like any other, leaving whoever waited on that history waiting. */
  stoppedShort?(): void;
}

export interface OlderBars {
  status: OlderBarsStatus;
  error: string | null;
  /** Ask for the candles older than what is drawn. Ignored while a read is in
   *  flight, after the archive ran out, and after a failure — a failure waits
   *  for `retry`, so a pan against a dead archive is not a request loop. */
  requestOlder(): void;
  /** Everything between `target` and the oldest drawn bar, in **one** read. A named moment is not a walk:
   *  reaching five months back through `requestOlder`'s ~day-per-page took 145 pages and gave up three weeks in. */
  reachBack(target: number): void;
  retry(): void;
}

/** How many of the oldest drawn bars define the span asked for — time the candles actually occupy, since a
 *  period-per-resolution table cannot hold a daily candle's session start and is blind to weekends besides. */
const PAGE_BARS = 300;

/**
 * Empty windows walked through before this pair counts as having no more history. One means nothing — a
 * weekend, a holiday and a pause in collection all look alike. Each doubles; four reached back only three days.
 */
const EMPTY_WINDOWS = 8;

/** Pages fetched for one request before it stops of its own accord. Only a source
 *  answering with a handful of candles per window gets anywhere near this; it exists so a
 *  pathological one cannot spin. */
const MAX_PAGES = 20;

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
 * Older candles for one (symbol, resolution). Every read ends at the oldest *drawn* bar, so it touches only
 * settled periods: the live edge still comes from the subscription's snapshot alone (design.md of that change).
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

  // Each (source, symbol, resolution) gets its own run; the generation makes a late answer from the
  // previous one dead on arrival, the way the feed's `cancelled` flag does.
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
    // Two bars are the least that can say how long a page is worth asking for.
    if (readerRef.current.readSeries().length < 2) return;

    const generation = generationRef.current;
    // `??=` covers the one call that could beat the effect above to it; every
    // later call gets the controller that effect installed for this pair.
    const controller = (abortRef.current ??= new AbortController());
    busyRef.current = true;
    setStatus("loading");

    // Whether the appetite that started this run was met, as opposed to the page budget
    // running out under it.
    let satisfied = false;
    try {
      for (let page = 0; page < MAX_PAGES; page++) {
        const series = readerRef.current.readSeries();
        let cursor = series[0].time;
        let span = pageSpan(series);
        let bars: Bar[] = [];

        // Walk back until a window has candles in it. An empty one is a closed
        // market as often as it is the end of the archive.
        for (let window = 0; window < EMPTY_WINDOWS && bars.length === 0; window++) {
          bars = await source.history(
            { symbol, resolution, from: cursor - span, to: cursor },
            controller.signal,
          );
          if (generation !== generationRef.current) return;
          cursor -= span;
          span *= 2;
        }

        if (bars.length === 0) {
          blockedRef.current = true;
          setStatus("exhausted");
          return;
        }

        readerRef.current.deliver(bars);

        // A page that leaves the series starting where it started is a page of candles already drawn:
        // asking again asks the same question, so the archive counts as having nothing older.
        if (readerRef.current.readSeries()[0]?.time >= series[0].time) {
          blockedRef.current = true;
          setStatus("exhausted");
          return;
        }

        if (!readerRef.current.needsMore()) {
          satisfied = true;
          break;
        }
      }
      if (!satisfied) readerRef.current.stoppedShort?.();
      setStatus("idle");
    } catch (cause: unknown) {
      if (generation !== generationRef.current || controller.signal.aborted) return;
      blockedRef.current = true;
      setError(cause instanceof Error ? cause.message : "could not read older candles");
      setStatus("error");
    } finally {
      if (generation === generationRef.current) busyRef.current = false;
    }
  }, [source, symbol, resolution]);

  const reach = useCallback(
    async (target: number) => {
      if (busyRef.current || blockedRef.current) return;
      const series = readerRef.current.readSeries();
      if (series.length === 0) return;
      const oldest = series[0].time;
      // Already covered: the pursuit has nothing to wait for, and a read of an empty
      // window would answer "no candles" and be taken for the end of the archive.
      if (target >= oldest) return;

      const generation = generationRef.current;
      const controller = (abortRef.current ??= new AbortController());
      busyRef.current = true;
      setStatus("loading");

      try {
        const bars = await source.history(
          { symbol, resolution, from: target, to: oldest },
          controller.signal,
        );
        if (generation !== generationRef.current) return;

        if (bars.length === 0) {
          // Nothing in a window that was asked for by name. Unlike the walk above, there
          // is no "maybe the next window" to try: this *was* the window.
          blockedRef.current = true;
          setStatus("exhausted");
          return;
        }

        readerRef.current.deliver(bars);
        // One read is the whole attempt, so the wait is over either way. Without this, a target the archive
        // starts after would leave the waiter waiting, since a page that made *some* progress settles nothing.
        if (readerRef.current.needsMore()) readerRef.current.stoppedShort?.();
        setStatus("idle");
      } catch (cause: unknown) {
        if (generation !== generationRef.current || controller.signal.aborted) return;
        blockedRef.current = true;
        setError(cause instanceof Error ? cause.message : "could not read older candles");
        setStatus("error");
      } finally {
        if (generation === generationRef.current) busyRef.current = false;
      }
    },
    [source, symbol, resolution],
  );

  const loadRef = useRef(load);
  loadRef.current = load;
  const reachRef = useRef(reach);
  reachRef.current = reach;

  const requestOlder = useCallback(() => {
    void loadRef.current();
  }, []);

  const reachBack = useCallback((target: number) => {
    void reachRef.current(target);
  }, []);

  const retry = useCallback(() => {
    // Only a failure is retried. "Exhausted" is an answer, not an outage — the archive said there is
    // nothing older, and asking again asks the same question of the same data.
    if (status !== "error") return;
    blockedRef.current = false;
    setError(null);
    setStatus("idle");
    void loadRef.current();
  }, [status]);

  return { status, error, requestOlder, reachBack, retry };
}
