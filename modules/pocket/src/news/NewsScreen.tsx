import { useEffect, useMemo, useRef, useState } from "react";
import { formatAge } from "../ui/age";
import { PULL_THRESHOLD } from "../ui/pull";
import { Pill } from "../ui/Pill";
import { usePullToRefresh } from "../ui/usePullToRefresh";
import type { NewsApi, NewsItem, NewsSource } from "./api";
import { formatDelay, formatSourceDelay } from "./delay";
import { directionLabel, sortItems, type SortDirection, type SortKey } from "./sort";
import { useNews } from "./useNews";
import { DEFAULT_MINUTES, WINDOWS, windowLabel } from "./window";
import styles from "./NewsScreen.module.css";

const SORT_KEYS: { key: SortKey; label: string }[] = [
  { key: "published", label: "Published" },
  { key: "seen", label: "Seen" },
  { key: "waited", label: "Waited" },
];
const FILTER_DEBOUNCE_MS = 300;

/** Nothing has a recent successful fetch: an empty list then means the collection, not a quiet hour. */
function stalled(sources: NewsSource[] | null): boolean {
  return sources !== null && sources.length > 0 && sources.every((s) => s.status !== "ok");
}

function expiry(item: NewsItem, now: Date): string | null {
  if (item.keptAt !== null) return "Kept";
  if (item.expiresAt === null) return null;
  return item.expiresAt.getTime() <= now.getTime()
    ? "Disappears at the next sweep"
    : `Disappears ${item.expiresAt.toLocaleString([], { dateStyle: "short", timeStyle: "short" })}`;
}

function NewsCard({ item, now, onKeep }: { item: NewsItem; now: Date; onKeep: (item: NewsItem) => void }) {
  const [open, setOpen] = useState(false);
  const kept = item.keptAt !== null;
  const note = expiry(item, now);
  const leadOnly = item.content === "";
  return (
    <article className={styles.card}>
      <button type="button" className={styles.toggle} aria-expanded={open} onClick={() => setOpen((was) => !was)}>
        <span className={styles.meta}>
          <span className={styles.publisher}>{item.publisher}</span>
          <span className={styles.when}>
            {item.publishedAt === null ? "no publish time" : formatAge(item.publishedAt, now)}
          </span>
        </span>
        <span className={styles.title}>{item.title}</span>
        {open ? (
          <span className={styles.body}>{leadOnly ? item.summary : item.content}</span>
        ) : (
          item.summary !== "" && <span className={styles.summary}>{item.summary}</span>
        )}
        <span className={styles.delay}>Delay {formatDelay(item)}</span>
      </button>
      {open && leadOnly && (
        <p className={styles.leadOnly}>The feed carries only a lead — the full text is at the source.</p>
      )}
      <div className={styles.actions}>
        {open && item.url !== null ? (
          <a className={styles.link} href={item.url} target="_blank" rel="noopener noreferrer">
            Open original
          </a>
        ) : (
          <span />
        )}
        <button
          type="button"
          className={kept ? styles.keepOn : styles.keep}
          aria-pressed={kept}
          onClick={() => onKeep(item)}
        >
          {kept ? "Kept" : "Keep"}
        </button>
      </div>
      {note !== null && !kept && <p className={styles.expiry}>{note}</p>}
    </article>
  );
}

function SourceRow({ source, now }: { source: NewsSource; now: Date }) {
  const flagged = source.status === "failing" || source.status === "stale";
  return (
    <li className={flagged ? styles.sourceFlagged : styles.source}>
      <div className={styles.sourceHead}>
        <span className={styles.publisher}>{source.publisher}</span>
        <Pill tone={source.status === "ok" ? "ok" : flagged ? "warn" : "muted"}>{source.status}</Pill>
      </div>
      {flagged && (
        <p className={styles.warning}>
          {source.lastFailure ?? "no successful fetch"} · last success {formatAge(source.lastSuccessAt, now)}
        </p>
      )}
      <p className={styles.sourceFigures}>
        {source.items24h} items / 24 h · newest{" "}
        {source.newestPublishedAt === null ? "n/a" : formatAge(source.newestPublishedAt, now)}
      </p>
      <p className={styles.sourceFigures}>
        Lower bound median / p90: {formatSourceDelay(source.delayMinMedianSeconds, source.delayMinP90Seconds)}
      </p>
      <p className={styles.sourceFigures}>
        Upper bound median / p90: {formatSourceDelay(source.delayMaxMedianSeconds, source.delayMaxP90Seconds)}
      </p>
    </li>
  );
}

/** Headlines with the delay they arrived with, on a phone. The sources are one tap away because
 *  "can I trust this list" is asked less often than "what happened". */
export function NewsScreen({ api, active = true }: { api: NewsApi; active?: boolean }) {
  const [minutes, setMinutes] = useState<number>(DEFAULT_MINUTES);
  const [sortKey, setSortKey] = useState<SortKey>("published");
  const [direction, setDirection] = useState<SortDirection>("desc");
  const [kept, setKept] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [sheet, setSheet] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), FILTER_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const view = useMemo(() => ({ minutes, q, kept }), [minutes, q, kept]);
  const news = useNews(api, view, active);
  const { list, sources, now } = news;

  const items = useMemo(
    () => (list === null ? [] : sortItems(list.items, sortKey, direction)),
    [list, sortKey, direction],
  );

  const scroller = useRef<HTMLDivElement>(null);
  const pull = usePullToRefresh(scroller, news.refresh);

  const windowName = kept ? "kept" : windowLabel(minutes);
  const trouble = sources?.filter((s) => s.status === "failing" || s.status === "stale").length ?? 0;
  const freshness = news.refreshing
    ? "reading…"
    : news.lastReadAt === null
      ? "not read yet"
      : `updated ${formatAge(news.lastReadAt, now)}`;

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <h1 className={styles.heading}>News</h1>
        <button type="button" className={styles.freshness} onClick={news.refresh}>
          {freshness}
          {list !== null && ` · ${list.count} · ${windowName}`}
        </button>
        <div className={styles.controls}>
          {WINDOWS.map((option) => (
            <button
              key={option.minutes}
              type="button"
              className={!kept && minutes === option.minutes ? styles.chipOn : styles.chip}
              aria-pressed={!kept && minutes === option.minutes}
              onClick={() => {
                setKept(false);
                setMinutes(option.minutes);
              }}
            >
              {option.chip}
            </button>
          ))}
          <button
            type="button"
            className={kept ? styles.chipOn : styles.chip}
            aria-pressed={kept}
            onClick={() => setKept((was) => !was)}
          >
            Kept
          </button>
          <button
            type="button"
            className={trouble > 0 ? styles.chipWarn : styles.chip}
            aria-expanded={sheet}
            onClick={() => setSheet((was) => !was)}
          >
            Sources{trouble > 0 ? ` (${trouble} down)` : ""}
          </button>
        </div>
        <div className={styles.controls} role="group" aria-label="Sort">
          {SORT_KEYS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={sortKey === option.key ? styles.chipOn : styles.chip}
              aria-pressed={sortKey === option.key}
              onClick={() => setSortKey(option.key)}
            >
              {option.label}
            </button>
          ))}
          <button
            type="button"
            className={styles.chip}
            aria-label="Sort direction"
            onClick={() => setDirection((was) => (was === "desc" ? "asc" : "desc"))}
          >
            {directionLabel(sortKey, direction)}
          </button>
        </div>
        <input
          className={styles.filter}
          type="search"
          value={text}
          placeholder="Filter headlines"
          aria-label="Filter headlines"
          onChange={(event) => setText(event.target.value)}
        />
      </header>

      <div className={styles.scroller} ref={scroller}>
        <div
          className={[styles.pull, pull >= PULL_THRESHOLD ? styles.pullReady : styles.pullPending].join(" ")}
          style={{ height: pull }}
        >
          {pull > 0 && (pull >= PULL_THRESHOLD ? "Release to refresh" : "Pull to refresh")}
        </div>

        {news.newsError !== null && <p className={styles.error}>{news.newsError}</p>}
        {news.keepError !== null && (
          <p className={styles.error} role="alert">
            {news.keepError}
          </p>
        )}

        {sheet && (
          <section className={styles.sheet} aria-label="Sources">
            {news.sourcesError !== null && <p className={styles.error}>{news.sourcesError}</p>}
            {sources === null ? (
              <p className={styles.note}>Reading the sources…</p>
            ) : (
              <ul className={styles.sources}>
                {sources.map((source) => (
                  <SourceRow key={source.source} source={source} now={now} />
                ))}
              </ul>
            )}
          </section>
        )}

        {list === null && news.newsError === null && <p className={styles.note}>Reading the news…</p>}

        {list !== null && list.truncated && (
          <p className={styles.warning}>
            The list is cut: the window holds more than this answer carries, and these are the newest.
          </p>
        )}

        {list !== null && list.items.length === 0 &&
          (stalled(sources) && !kept ? (
            <p className={styles.warning}>
              Collection is stalled: no source has a recent successful fetch, so an empty list says
              nothing about the news.
            </p>
          ) : (
            <p className={styles.note}>
              {kept ? "Nothing is kept." : `No headlines in the ${windowName}.`}
            </p>
          ))}

        <div className={styles.list}>
          {items.map((item) => (
            <NewsCard key={`${item.source}:${item.externalId}`} item={item} now={now} onKeep={news.toggleKeep} />
          ))}
        </div>
      </div>
    </div>
  );
}
