import { useCallback } from "react";
import type { MarketDataSource } from "../data/source";
import type { Instrument } from "../data/types";
import { useAsyncOptions } from "../ui/useAsyncOptions";

export const DEBOUNCE_MS = 250;

export type SearchStatus = "idle" | "searching" | "results" | "no-results" | "error";

export interface SearchState {
  status: SearchStatus;
  instruments: Instrument[];
  error: string | null;
}

/**
 * Search-as-you-type without a request per keystroke, on top of the debounce
 * and stale-response guard every autocomplete in the terminal shares
 * (`useAsyncOptions`) — an empty query stays idle rather than searching
 * (terminal-instruments spec, "Pisanie w polu wyszukiwania").
 */
export function useInstrumentSearch(source: MarketDataSource, query: string): SearchState {
  const trimmed = query.trim();
  const fetch = useCallback(
    (q: string, signal: AbortSignal) =>
      source.searchInstruments(q, signal).then((instruments) => ({ options: instruments })),
    [source],
  );
  const state = useAsyncOptions<Instrument>(fetch, trimmed, {
    debounceMs: DEBOUNCE_MS,
    enabled: trimmed !== "",
  });

  return {
    status: state.status === "loading" ? "searching" : state.status,
    instruments: state.options,
    error: state.error,
  };
}
