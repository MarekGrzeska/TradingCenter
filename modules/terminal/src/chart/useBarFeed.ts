import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketDataSource } from "../data/source";
import type { Bar, ConnectionState, Resolution } from "../data/types";

export type FeedStatus = "loading" | "ready" | "empty" | "error";

export interface BarSink {
  /** The whole history, replacing whatever was drawn. */
  onHistory(bars: Bar[]): void;
  /** One live bar, to be merged by timestamp into what is already drawn. */
  onBar(bar: Bar): void;
}

export interface BarFeed {
  status: FeedStatus;
  error: string | null;
  streamState: ConnectionState;
  retry(): void;
}

export const HISTORY_BARS = 500;

/**
 * Owns one (symbol, resolution) feed: pull the history, then keep it current
 * from the stream. Bars are handed to `sink` imperatively and never held in
 * React state — six slots at roughly five quotes a second each would otherwise
 * re-render the tree ~30 times a second (design.md, "Wykres pisze do canvasu,
 * nie do stanu Reacta"). Only what changes rarely — status, error, connection
 * state — lives in state here.
 */
export function useBarFeed(
  source: MarketDataSource,
  symbol: string,
  resolution: Resolution,
  sink: BarSink,
): BarFeed {
  const [status, setStatus] = useState<FeedStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<ConnectionState>("connecting");
  const [attempt, setAttempt] = useState(0);

  // The sink is recreated on every parent render; keeping it in a ref means a
  // parent re-render never tears down the subscription.
  const sinkRef = useRef(sink);
  sinkRef.current = sink;

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    // Each effect run owns this flag and its cleanup sets it. A resolution
    // switched three times in quick succession therefore draws the last one,
    // not whichever response happens to land last — AbortController alone
    // does not cover that, since a response already queued as a microtask when
    // abort() fires still resolves. It also makes StrictMode's
    // mount/unmount/mount safe: the first run's late response is dead the
    // moment its cleanup ran.
    let cancelled = false;
    const controller = new AbortController();
    const isCurrent = () => !cancelled;

    setStatus("loading");
    setError(null);
    setStreamState("connecting");

    source
      .history({ symbol, resolution, count: HISTORY_BARS }, controller.signal)
      .then((bars) => {
        if (!isCurrent()) return;
        sinkRef.current.onHistory(bars);
        setStatus(bars.length === 0 ? "empty" : "ready");
      })
      .catch((cause: unknown) => {
        if (!isCurrent() || controller.signal.aborted) return;
        setStatus("error");
        setError(cause instanceof Error ? cause.message : "could not read history");
      });

    const unsubscribe = source.subscribe(symbol, resolution, (event) => {
      if (!isCurrent()) return;
      switch (event.kind) {
        case "bar":
          sinkRef.current.onBar(event.bar);
          break;
        case "status":
          setStreamState(event.state);
          break;
        case "error":
          setError(event.message);
          break;
        case "quote":
          break;
      }
    });

    return () => {
      cancelled = true;
      controller.abort();
      unsubscribe();
    };
  }, [source, symbol, resolution, attempt]);

  return { status, error, streamState, retry };
}
