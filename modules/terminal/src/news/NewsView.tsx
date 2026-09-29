import { useEffect, useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { socialIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { NewsCard } from "./NewsCard";
import { SourcesPanel } from "./SourcesPanel";
import { collectionStalled, STATUS_TEXT } from "./delay";
import { createNewsApi, type NewsApi, type NewsPage, type NewsSource } from "./newsApi";

/**
 * Headlines as the feeds gave them, in the feeds' language, with how late each one reached this archive. No model
 * reads them yet. **An empty list is two different facts** — a window in which nothing was published, and
 * collection that has stopped — and the screen says which.
 */

/** Twice as often as the posts: a headline's value is in minutes, and the loop behind it ticks every 30 s. */
const NEWS_POLL_MS = 30_000;
const SOURCES_POLL_MS = 60_000;
const WINDOWS = [1, 6, 24] as const;
const DEFAULT_HOURS = 6;
const TEXT_DEBOUNCE_MS = 300;

const NO_PAGE: NewsPage = { items: [], truncated: false, windowFrom: null };
const NO_SOURCES: NewsSource[] = [];

const keyOf = (item: { source: string; externalId: string }) => `${item.source}\u0000${item.externalId}`;

export function NewsView({ api }: { api?: NewsApi } = {}) {
  const client = useMemo(
    () => api ?? createNewsApi(resolveEndpoints().socialHttp, socialIdentity),
    [api],
  );
  const [hours, setHours] = useState<number>(DEFAULT_HOURS);
  const [keptOnly, setKeptOnly] = useState(false);
  const [text, setText] = useState("");
  const [appliedText, setAppliedText] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  // What the operator asked for, ahead of the server's answer. Dropped when the server catches up.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const timer = setTimeout(() => setAppliedText(text), TEXT_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  const page = useRead<NewsPage>({
    key: ["news", "items", { hours, keptOnly, appliedText, chosen }],
    read: (signal) =>
      client.news({ hours, sources: chosen, text: appliedText, kept: keptOnly }, signal),
    initial: NO_PAGE,
    fallbackMessage: "could not read the news",
    pollMs: NEWS_POLL_MS,
    // A failed refresh must not take the headlines off a screen being read.
    onFailure: "keep",
  });

  const sources = useRead<NewsSource[]>({
    key: ["news", "sources"],
    read: (signal) => client.sources(signal),
    initial: NO_SOURCES,
    fallbackMessage: "could not read the state of the sources",
    pollMs: SOURCES_POLL_MS,
  });

  useEffect(() => {
    setPending((was) => {
      const next = { ...was };
      for (const item of page.value.items) {
        const key = keyOf(item);
        if (key in next && next[key] === (item.keptAt !== null)) delete next[key];
      }
      return Object.keys(next).length === Object.keys(was).length ? was : next;
    });
  }, [page.value]);

  async function keep(item: NewsPage["items"][number], keep: boolean) {
    const key = keyOf(item);
    setPending((was) => ({ ...was, [key]: keep }));
    setFailed((was) => ({ ...was, [key]: false }));
    try {
      await client.keep(item.source, item.externalId, keep, new AbortController().signal);
      page.reload();
    } catch {
      setPending((was) => {
        const { [key]: _dropped, ...rest } = was;
        return rest;
      });
      setFailed((was) => ({ ...was, [key]: true }));
    }
  }

  function toggleSource(source: string) {
    setChosen((was) => (was.includes(source) ? was.filter((s) => s !== source) : [...was, source]));
  }

  const ready = page.status === "ready";
  const items = page.value.items;
  const troubled = sources.value.filter((s) => s.status === "failing" || s.status === "stale");
  const stalled = sources.status === "ready" && collectionStalled(sources.value);

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">News</h1>
        <span className="text-xs text-ink-faint">
          {items.length} {items.length === 1 ? "news" : "newsów"} ·{" "}
          {keptOnly ? "zachowane" : `ostatnie ${hours} h`} · odświeżane co {NEWS_POLL_MS / 1000} s
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
          {!keptOnly &&
            WINDOWS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={hours === option}
                className={`rounded border px-2 py-0.5 ${
                  hours === option ? "border-accent text-accent" : "border-border text-ink-muted"
                }`}
                onClick={() => setHours(option)}
              >
                {option} h
              </button>
            ))}
          <button
            type="button"
            aria-pressed={keptOnly}
            className={`rounded border px-2 py-0.5 ${
              keptOnly ? "border-accent text-accent" : "border-border text-ink-muted"
            }`}
            onClick={() => setKeptOnly((was) => !was)}
          >
            zachowane
          </button>
          <input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="szukaj w tytule i leadzie"
            aria-label="szukaj w newsach"
            className="w-56 rounded border border-border bg-panel px-2 py-0.5 text-ink"
          />
        </div>
      </header>

      {sources.value.length > 0 && !keptOnly && (
        <div className="flex flex-wrap gap-1.5 text-xs" aria-label="źródła">
          {sources.value.map((source) => (
            <button
              key={source.source}
              type="button"
              aria-pressed={chosen.includes(source.source)}
              title={STATUS_TEXT[source.status]}
              className={`rounded border px-1.5 py-0.5 ${
                chosen.includes(source.source)
                  ? "border-accent text-accent"
                  : source.status === "ok"
                    ? "border-border text-ink-muted"
                    : "border-warning text-warning"
              }`}
              onClick={() => toggleSource(source.source)}
            >
              {source.source}
            </button>
          ))}
        </div>
      )}

      {page.error !== null && (
        <UnreachableNotice onRetry={page.reload}>{page.error}</UnreachableNotice>
      )}

      {page.value.truncated && (
        <p className="text-sm text-ink-muted">
          Lista jest obcięta: okno ma więcej newsów, niż zwrócono — widać najnowsze.
        </p>
      )}

      {troubled.length > 0 && (
        <p className="text-sm text-warning">
          {troubled.map((source) => (
            <span key={source.source}>
              {source.source}: {STATUS_TEXT[source.status]}
              {source.lastFailure !== null && ` — ${source.lastFailure}`}.{" "}
            </span>
          ))}
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {ready && items.length === 0 ? (
          <p className="text-sm text-ink-muted">
            {keptOnly
              ? "Nic nie jest zachowane."
              : stalled
                ? "Zbiór stoi: żadne źródło nie odpowiada. Pusta lista nie znaczy, że nic nie opublikowano."
                : `Brak newsów w ostatnich ${hours} h.`}
          </p>
        ) : (
          items.map((item) => (
            <NewsCard
              key={keyOf(item)}
              item={item}
              kept={pending[keyOf(item)] ?? item.keptAt !== null}
              failed={failed[keyOf(item)] === true}
              onKeep={(next) => void keep(item, next)}
            />
          ))
        )}

        <button
          type="button"
          className="self-start text-xs text-ink-faint underline"
          aria-expanded={sourcesOpen}
          onClick={() => setSourcesOpen((was) => !was)}
        >
          {sourcesOpen ? "▲" : "▼"} Źródła i ich opóźnienia ({sources.value.length})
        </button>
        {sourcesOpen && <SourcesPanel sources={sources.value} />}
      </div>
    </section>
  );
}
