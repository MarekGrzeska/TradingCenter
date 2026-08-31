import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketDataSource } from "../data/source";
import type { Bar, ConnectionState, Resolution } from "../data/types";

export type FeedStatus = "loading" | "ready" | "empty" | "error";

export interface BarSink {
  /** The whole series as the source has it, to be merged into what is drawn. */
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

/**
 * Owns one (symbol, resolution) feed: nothing is spliced, the subscription's first message *is* the history.
 * Bars go to `sink` imperatively — six slots at five quotes a second would re-render the tree thirty times.
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
    // Each effect run owns this flag and its cleanup sets it, so a resolution switched three times draws
    // the last one — and StrictMode's mount/unmount/mount is safe for the same reason.
    let cancelled = false;

    setStatus("loading");
    setError(null);
    setStreamState("connecting");

    const unsubscribe = source.subscribe(symbol, resolution, (event) => {
      if (cancelled) return;
      switch (event.kind) {
        case "snapshot":
          sinkRef.current.onHistory(event.bars);
          if (event.forming) {
            // Separate from the settled series because it means something different: the period still
            // moving, which the next message will move again.
            sinkRef.current.onBar(event.forming);
          }
          setStatus(event.bars.length === 0 && !event.forming ? "empty" : "ready");
          // A snapshot that arrives after a refusal-then-retry supersedes the refusal; leaving the old
          // message up would contradict the candles now on screen.
          setError(null);
          break;
        case "bar":
          sinkRef.current.onBar(event.bar);
          break;
        case "status":
          setStreamState(event.state);
          break;
        case "error":
          // Named by the source — an unknown symbol, a pair nobody collects, the archive unreachable. A
          // subscription that fails before its snapshot has nothing to draw, so this is the whole answer.
          setError(event.message);
          setStatus((current) => (current === "loading" ? "error" : current));
          break;
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [source, symbol, resolution, attempt]);

  return { status, error, streamState, retry };
}
