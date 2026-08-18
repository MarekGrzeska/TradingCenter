import { QueryClient, useQuery, type QueryKey } from "@tanstack/react-query";
import { useCallback } from "react";

/**
 * The one client every read in the terminal goes through.
 *
 * It is passed to `useQuery` explicitly rather than hung on a `QueryClientProvider`,
 * and that is deliberate: the tests render views directly — `render(<InstrumentsView />)`
 * — so a provider would be a wrapper repeated in every test file, carrying no behaviour
 * of its own. `src/test/setup.ts` clears the cache between tests and turns retries off
 * there, which is the only thing a per-test client would have bought.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A back end that is not running is a normal state here (see `vite.config.ts`),
      // and four backoffs of it hold the view in "loading" for seconds. One retry,
      // quickly — enough to ride out a restart, short enough to report the truth.
      retry: 1,
      retryDelay: 400,
      // The terminal polls what needs polling on its own interval; a tab regaining
      // focus is not news about the archive.
      refetchOnWindowFocus: false,
    },
  },
});

export type ReadStatus = "loading" | "ready" | "error";

/** One read, with a way to ask again — the shape the hand-written hooks already had. */
export interface Read<T> {
  status: ReadStatus;
  value: T;
  /** Why the last attempt failed. Never a raw transport error. */
  error: string | null;
  reload(): void;
}

export interface ReadOptions<T> {
  /** What distinguishes this read from every other one — the cache key. */
  key: QueryKey;
  read(signal: AbortSignal): Promise<T>;
  /** What the view renders before the first answer. Must be a stable value: a fresh
   *  `[]` per render is a fresh identity per render for everything downstream. */
  initial: T;
  /** Said instead of a transport error when the failure carries no message. */
  fallbackMessage: string;
  /** Set to re-ask on an interval. Absent means once, plus whatever `reload()` asks for. */
  pollMs?: number;
  enabled?: boolean;
  /** What happens to an answer already on screen when a re-read fails.
   *
   *  `"keep"` — the default — reports the failure beside rows that are still worth
   *  reading. `"forget"` drops them, and is for the reads where a stale answer taken
   *  for a current one is itself the failure: the cost tab MUST NOT show numbers from
   *  before an outage as current (`terminal-agent-cost` spec). */
  onFailure?: "keep" | "forget";
}

/**
 * A read of a back end, cached, deduplicated and retried by TanStack Query.
 *
 * `status` keeps "nothing there" apart from "nobody could be asked" — both are an empty
 * array, and only one means the operator has nothing set up. A failed re-read does not
 * blank what is already on screen: once an answer has arrived the status stays `ready`
 * and the failure is reported beside the rows, because slightly stale rows beat an error
 * where real data was.
 */
export function useRead<T>({
  key,
  read,
  initial,
  fallbackMessage,
  pollMs,
  enabled = true,
  onFailure = "keep",
}: ReadOptions<T>): Read<T> {
  const query = useQuery(
    {
      queryKey: key,
      queryFn: ({ signal }) => read(signal),
      refetchInterval: pollMs,
      enabled,
    },
    queryClient,
  );

  const { refetch } = query;
  const reload = useCallback(() => void refetch(), [refetch]);

  const failed = query.error !== null;
  const forgotten = failed && onFailure === "forget";
  const answered = query.data !== undefined && !forgotten;

  return {
    status: answered ? "ready" : failed ? "error" : "loading",
    value: forgotten ? initial : (query.data ?? initial),
    error: failed ? messageOf(query.error, fallbackMessage) : null,
    reload,
  };
}

/** What the operator is told. A rejection that is not an `Error` says nothing useful. */
export function messageOf(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
