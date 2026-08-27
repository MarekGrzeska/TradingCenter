import { QueryClient, useQuery, type QueryKey } from "@tanstack/react-query";
import { useCallback } from "react";

/**
 * Passed to `useQuery` explicitly rather than hung on a provider: the tests render views directly, so a provider
 * would be a wrapper in every test file. `src/test/setup.ts` clears the cache and turns retries off there.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A back end that is not running is a normal state here (see `vite.config.ts`), and four backoffs hold
      // the view in "loading" for seconds. One retry: enough to ride out a restart, short enough to be honest.
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
  /** `"keep"` reports the failure beside rows still worth reading. `"forget"` is for reads where a stale answer
   *  taken for a current one is itself the failure — the cost tab MUST NOT show pre-outage numbers as current. */
  onFailure?: "keep" | "forget";
}

/**
 * `status` keeps "nothing there" apart from "nobody could be asked" — both are an empty array, and only one means
 * the operator has nothing set up. A failed re-read reports beside the rows rather than blanking them.
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
