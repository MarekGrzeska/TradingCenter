import { useEffect, useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { socialIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { NewsCard } from "./NewsCard";
import { SourcesPanel } from "./SourcesPanel";
import { collectionStalled, STATUS_TEXT } from "./delay";
import { directionLabel, SORT_LABELS, sortItems, type SortDirection, type SortKey } from "./sort";
import { DEFAULT_MINUTES, windowName, WINDOWS } from "./windows";
import { createNewsApi, type NewsApi, type NewsPage, type NewsSource } from "./newsApi";

/**
 * Headlines as the feeds gave them, in the feeds' language, with how late each one reached this archive. No model
 * reads them yet. **An empty list is two different facts** — a window in which nothing was published, and
 * collection that has stopped — and the screen says which.
 */

/** Twice as often as the posts: a headline's value is in minutes, and the loop behind it ticks every 30 s. */
const NEWS_POLL_MS = 30_000;
const SOURCES_POLL_MS = 60_000;
const TEXT_DEBOUNCE_MS = 300;

const NO_PAGE: NewsPage = { items: [], truncated: false, windowFrom: null };
const NO_SOURCES: NewsSource[] = [];

const keyOf = (item: { source: string; externalId: string }) => `${item.source}\u0000${item.externalId}`;

export function NewsView({ api }: { api?: NewsApi } = {}) {
  const client = useMemo(
    () => api ?? createNewsApi(resolveEndpoints().socialHttp, socialIdentity),
    [api],
  );
  const [minutes, setMinutes] = useState<number>(DEFAULT_MINUTES);
  const [keptOnly, setKeptOnly] = useState(false);
  const [text, setText] = useState("");
  const [appliedText, setAppliedText] = useState("");
  // Which sources are switched OFF. Everything starts on, so a source that appears later is on too.
  const [excluded, setExcluded] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("published");
  const [direction, setDirection] = useState<SortDirection>("desc");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  // What the operator asked for, ahead of the server's answer. Dropped when the server catches up.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const timer = setTimeout(() => setAppliedText(text), TEXT_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  const sources = useRead<NewsSource[]>({
    key: ["news", "sources"],
    read: (signal) => client.sources(signal),
    initial: NO_SOURCES,
    fallbackMessage: "could not read the state of the sources",
    pollMs: SOURCES_POLL_MS,
  });

  const allIds = sources.value.map((source) => source.source);
  const selected = allIds.filter((id) => !excluded.includes(id));
  const noneSelected = allIds.length > 0 && selected.length === 0;
  // No filter at all while everything is on: an unfiltered read also covers a source the table has not listed yet.
  const sourceFilter = excluded.length === 0 ? [] : selected;

  const page = useRead<NewsPage>({
    key: ["news", "items", { minutes, keptOnly, appliedText, sourceFilter }],
    read: (signal) =>
      client.news({ minutes, sources: sourceFilter, text: appliedText, kept: keptOnly }, signal),
    // An empty list of sources means "all" on the wire, so choosing none must not be asked at all.
    enabled: keptOnly || !noneSelected,
    initial: NO_PAGE,
    fallbackMessage: "could not read the news",
    pollMs: NEWS_POLL_MS,
    // A failed refresh must not take the headlines off a screen being read.
    onFailure: "keep",
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
    setExcluded((was) => (was.includes(source) ? was.filter((s) => s !== source) : [...was, source]));
  }

  const ready = page.status === "ready";
  const items = useMemo(
    () => sortItems(page.value.items, sortKey, direction),
    [page.value.items, sortKey, direction],
  );
  const troubled = sources.value.filter((s) => s.status === "failing" || s.status === "stale");
  const stalled = sources.status === "ready" && collectionStalled(sources.value);

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">News</h1>
        <span className="text-xs text-ink-faint">
          {items.length} {items.length === 1 ? "news" : "newsów"} ·{" "}
          {keptOnly ? "zachowane" : windowName(minutes)} · odświeżane co {NEWS_POLL_MS / 1000} s
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
          {!keptOnly &&
            WINDOWS.map((option) => (
              <button
                key={option.minutes}
                type="button"
                aria-pressed={minutes === option.minutes}
                className={`rounded border px-2 py-0.5 ${
                  minutes === option.minutes
                    ? "border-accent text-accent"
                    : "border-border text-ink-muted"
                }`}
                onClick={() => setMinutes(option.minutes)}
              >
                {option.label}
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
          <span className="flex items-center gap-1" role="group" aria-label="sortowanie">
            {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={sortKey === key}
                className={`rounded border px-2 py-0.5 ${
                  sortKey === key ? "border-accent text-accent" : "border-border text-ink-muted"
                }`}
                onClick={() => setSortKey(key)}
              >
                {SORT_LABELS[key]}
              </button>
            ))}
            <button
              type="button"
              className="rounded border border-border px-2 py-0.5 text-ink-muted"
              onClick={() => setDirection((was) => (was === "desc" ? "asc" : "desc"))}
            >
              {directionLabel(sortKey, direction)}
            </button>
          </span>
        </div>
      </header>

      {sources.value.length > 0 && !keptOnly && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs" role="group" aria-label="źródła">
          <button
            type="button"
            className="rounded border border-border px-2 py-0.5 text-ink"
            onClick={() => setExcluded([])}
          >
            Wszystkie
          </button>
          <button
            type="button"
            className="rounded border border-border px-2 py-0.5 text-ink-muted"
            onClick={() => setExcluded(allIds)}
          >
            Żadne
          </button>
          <button
            type="button"
            className="rounded border border-border px-2 py-0.5 text-ink-muted"
            title="wyłącza źródła, które nie odpowiadają"
            onClick={() =>
              setExcluded(sources.value.filter((s) => s.status !== "ok").map((s) => s.source))
            }
          >
            Tylko działające
          </button>
          <span className="mx-1 h-4 border-l border-border" aria-hidden />
          {sources.value.map((source) => {
            const on = !excluded.includes(source.source);
            return (
              <button
                key={source.source}
                type="button"
                aria-pressed={on}
                title={STATUS_TEXT[source.status]}
                className={`rounded border px-1.5 py-0.5 ${
                  !on
                    ? "border-border text-ink-faint line-through"
                    : source.status === "ok"
                      ? "border-accent text-accent"
                      : "border-warning text-warning"
                }`}
                onClick={() => toggleSource(source.source)}
              >
                {source.source}
                <span className="ml-1 tabular-nums text-ink-faint">{source.items24h}</span>
              </button>
            );
          })}
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
        {!keptOnly && noneSelected ? (
          <p className="text-sm text-ink-muted">
            Nie wybrano żadnego źródła. Użyj „Wszystkie”, żeby zobaczyć newsy.
          </p>
        ) : ready && items.length === 0 ? (
          <p className="text-sm text-ink-muted">
            {keptOnly
              ? "Nic nie jest zachowane."
              : stalled
                ? "Zbiór stoi: żadne źródło nie odpowiada. Pusta lista nie znaczy, że nic nie opublikowano."
                : `Brak newsów: ${windowName(minutes)}.`}
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
