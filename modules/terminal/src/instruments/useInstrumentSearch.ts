import { useEffect, useState } from "react";
import type { MarketDataSource } from "../data/source";
import type { Instrument } from "../data/types";

export const DEBOUNCE_MS = 250;

export type SearchStatus = "idle" | "searching" | "results" | "no-results" | "error";

export interface SearchState {
  status: SearchStatus;
  instruments: Instrument[];
  error: string | null;
}

/**
 * Search-as-you-type without a request per keystroke: the query settles for
 * `DEBOUNCE_MS` first, and each run owns a flag its cleanup sets, so a slow
 * answer to an earlier query can never overwrite the current one
 * (terminal-instruments spec, "Pisanie w polu wyszukiwania"). Same reasoning as
 * the chart feed — an abort does not un-queue a response already resolved.
 */
export function useInstrumentSearch(source: MarketDataSource, query: string): SearchState {
  const [state, setState] = useState<SearchState>({
    status: "idle",
    instruments: [],
    error: null,
  });

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setState({ status: "idle", instruments: [], error: null });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, status: "searching", error: null }));

    const timer = setTimeout(() => {
      source
        .searchInstruments(trimmed, controller.signal)
        .then((instruments) => {
          if (cancelled) return;
          setState({
            status: instruments.length === 0 ? "no-results" : "results",
            instruments,
            error: null,
          });
        })
        .catch((cause: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          setState({
            status: "error",
            instruments: [],
            error: cause instanceof Error ? cause.message : "search failed",
          });
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [source, query]);

  return state;
}
