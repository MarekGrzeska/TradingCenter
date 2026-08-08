import { useEffect, useRef, useState } from "react";

export type AsyncOptionsStatus = "idle" | "loading" | "results" | "no-results" | "error";

export interface AsyncOptionsState<T> {
  status: AsyncOptionsStatus;
  options: T[];
  /** True when the source cut its answer short — there is more than what
   *  came back, not merely nothing else. */
  truncated: boolean;
  error: string | null;
}

export interface OptionsPage<T> {
  options: T[];
  truncated?: boolean;
}

export type OptionsFetcher<T> = (query: string, signal: AbortSignal) => Promise<OptionsPage<T>>;

const IDLE: AsyncOptionsState<never> = { status: "idle", options: [], truncated: false, error: null };

/**
 * Debounce plus protection against a stale answer overtaking a newer one:
 * each run owns a `cancelled` flag its cleanup sets, so a slow response to an
 * earlier query can never land after a faster response to a later one. This
 * is the logic every autocomplete in the terminal shares (terminal-instruments
 * spec, "Pisanie w polu wyszukiwania"; "Podpowiadanie zachowuje się wszędzie
 * tak samo").
 *
 * `fetch` is read through a ref rather than listed as a dependency, the same
 * way `useBarFeed` holds its sink — a caller's inline closure is recreated
 * every render, and refetching on that would defeat the debounce entirely.
 * Only `query`, `enabled`, and `retry()` are meant to restart the fetch.
 */
export function useAsyncOptions<T>(
  fetch: OptionsFetcher<T>,
  query: string,
  { debounceMs = 250, enabled = true }: { debounceMs?: number; enabled?: boolean } = {},
): AsyncOptionsState<T> & { retry(): void } {
  const [state, setState] = useState<AsyncOptionsState<T>>(IDLE);
  const [attempt, setAttempt] = useState(0);
  const fetchRef = useRef(fetch);
  fetchRef.current = fetch;

  useEffect(() => {
    if (!enabled) {
      setState(IDLE);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, status: "loading", error: null }));

    const timer = setTimeout(() => {
      fetchRef
        .current(query, controller.signal)
        .then((page) => {
          if (cancelled) return;
          setState({
            status: page.options.length === 0 ? "no-results" : "results",
            options: page.options,
            truncated: page.truncated ?? false,
            error: null,
          });
        })
        .catch((cause: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          setState({
            status: "error",
            options: [],
            truncated: false,
            error: cause instanceof Error ? cause.message : "fetching options failed",
          });
        });
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, enabled, debounceMs, attempt]);

  return { ...state, retry: () => setAttempt((n) => n + 1) };
}
