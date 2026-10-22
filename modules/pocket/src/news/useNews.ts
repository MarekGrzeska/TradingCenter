import { useCallback, useEffect, useRef, useState } from "react";
import type { NewsApi, NewsItem, NewsList, NewsSource } from "./api";
import { limitFor } from "./window";

/** Both reads. The feeds are fetched every minute or so, so a phone asking faster only redraws. */
export const POLL_MS = 60_000;
const TICK_MS = 30_000;


export interface NewsView {
  minutes: number;
  q: string;
  kept: boolean;
}

interface Polled<T> {
  data: T | null;
  error: string | null;
  refreshing: boolean;
  lastReadAt: Date | null;
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The news archive could not be read.";
}

/** A hidden document does not poll (a phone in a pocket has nobody reading), and a failed read sets
 *  `error` beside `data` instead of clearing it. Data belongs to the `key` it was read for. */
function usePoll<T>(
  read: (signal: AbortSignal) => Promise<T>,
  key: string,
  active: boolean,
  pollMs: number,
) {
  const [state, setState] = useState<Polled<T> & { key: string }>({
    key,
    data: null,
    error: null,
    refreshing: false,
    lastReadAt: null,
  });
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt((value) => value + 1), []);
  const reader = useRef(read);
  reader.current = read;

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let cancelled = false;

    const load = async () => {
      setState((was) => ({ ...was, key, refreshing: true, data: was.key === key ? was.data : null }));
      try {
        const data = await reader.current(controller.signal);
        if (cancelled) return;
        setState({ key, data, error: null, refreshing: false, lastReadAt: new Date() });
      } catch (cause) {
        if (cancelled || controller.signal.aborted) return;
        setState((was) => ({ ...was, key, error: messageOf(cause), refreshing: false }));
      }
    };

    void load();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, pollMs);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [key, active, pollMs, attempt]);

  return { ...state, data: state.key === key ? state.data : null, refresh };
}

const idOf = (item: Pick<NewsItem, "source" | "externalId">) => `${item.source}\u0000${item.externalId}`;

export function useNews(api: NewsApi, view: NewsView, active: boolean, pollMs: number = POLL_MS) {
  const news = usePoll<NewsList>(
    (signal) =>
      api.getNews(
        view.kept ? { kept: true } : { minutes: view.minutes, q: view.q || undefined, limit: limitFor(view.minutes) },
        signal,
      ),
    `${view.kept}|${view.minutes}|${view.q}`,
    active,
    pollMs,
  );
  const sources = usePoll<NewsSource[]>((signal) => api.getNewsSources(signal), "sources", active, pollMs);

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const ticking = window.setInterval(() => setNow(new Date()), TICK_MS);
    return () => window.clearInterval(ticking);
  }, []);

  // Items as the last write left them, laid over what the poll read until the next poll catches up.
  const [overrides, setOverrides] = useState<Record<string, NewsItem>>({});
  const inflight = useRef(new Set<string>());
  const [keepError, setKeepError] = useState<string | null>(null);
  const lastReadAt = news.lastReadAt;
  useEffect(() => {
    setOverrides((was) => Object.fromEntries(Object.entries(was).filter(([id]) => inflight.current.has(id))));
  }, [lastReadAt]);

  const toggleKeep = useCallback(
    async (item: NewsItem) => {
      const id = idOf(item);
      const keep = item.keptAt === null;
      inflight.current.add(id);
      setKeepError(null);
      setOverrides((was) => ({
        ...was,
        [id]: { ...item, keptAt: keep ? new Date() : null, expiresAt: keep ? null : item.expiresAt },
      }));
      try {
        const saved = await api.setKept(item.source, item.externalId, keep);
        setOverrides((was) => ({ ...was, [id]: saved }));
      } catch (cause) {
        setOverrides((was) => {
          const { [id]: _reverted, ...rest } = was;
          return rest;
        });
        setKeepError(`Could not ${keep ? "keep" : "unkeep"} “${item.title}”: ${messageOf(cause)}`);
      } finally {
        inflight.current.delete(id);
      }
    },
    [api],
  );

  const items = news.data === null ? null : news.data.items.map((item) => overrides[idOf(item)] ?? item);

  return {
    list: news.data === null ? null : { ...news.data, items: items ?? [] },
    sources: sources.data,
    newsError: news.error,
    sourcesError: sources.error,
    refreshing: news.refreshing,
    lastReadAt: news.lastReadAt,
    now,
    refresh: () => {
      news.refresh();
      sources.refresh();
    },
    toggleKeep,
    keepError,
    dismissKeepError: () => setKeepError(null),
  };
}
