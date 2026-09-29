import { useEffect, useMemo, useRef, useState } from "react";
import { formatAge } from "../ui/age";
import { PULL_THRESHOLD } from "../ui/pull";
import { Pill } from "../ui/Pill";
import { usePullToRefresh } from "../ui/usePullToRefresh";
import type { NewsApi, NewsItem, NewsSource } from "./api";
import { formatDelay, formatSourceDelay } from "./delay";
import { useNews } from "./useNews";
import styles from "./NewsScreen.module.css";

const WINDOWS = [1, 6, 24] as const;
const DEFAULT_HOURS = 6;
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
  const kept = item.keptAt !== null;
  const note = expiry(item, now);
  return (
    <article className={styles.card}>
      <div className={styles.meta}>
        <span className={styles.publisher}>{item.publisher}</span>
        <span className={styles.when}>
          {item.publishedAt === null ? "no publish time" : formatAge(item.publishedAt, now)}
        </span>
      </div>
      <h2 className={styles.title}>{item.title}</h2>
      {item.summary !== "" && <p className={styles.summary}>{item.summary}</p>}
      <p className={styles.delay}>Delay {formatDelay(item)}</p>
      <div className={styles.actions}>
        {item.url !== null && (
          <a className={styles.link} href={item.url} target="_blank" rel="noopener noreferrer">
            Open original
          </a>
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
  const [hours, setHours] = useState<number>(DEFAULT_HOURS);
  const [kept, setKept] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [sheet, setSheet] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), FILTER_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const view = useMemo(() => ({ hours, q, kept }), [hours, q, kept]);
  const news = useNews(api, view, active);
  const { list, sources, now } = news;

  const scroller = useRef<HTMLDivElement>(null);
  const pull = usePullToRefresh(scroller, news.refresh);

  const windowName = kept ? "kept" : `last ${hours} h`;
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
              key={option}
              type="button"
              className={!kept && hours === option ? styles.chipOn : styles.chip}
              aria-pressed={!kept && hours === option}
              onClick={() => {
                setKept(false);
                setHours(option);
              }}
            >
              {option} h
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
          {list?.items.map((item) => (
            <NewsCard key={`${item.source}:${item.externalId}`} item={item} now={now} onKeep={news.toggleKeep} />
          ))}
        </div>
      </div>
    </div>
  );
}
