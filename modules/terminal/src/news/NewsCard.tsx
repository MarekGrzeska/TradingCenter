import { formatInstant } from "../ui/formatTime";
import { delayText } from "./delay";
import type { NewsItem } from "./newsApi";

/** One headline: the feed's own words, when it said them, how late that reached us, and whether to keep it. */

export function NewsCard({
  item,
  kept,
  failed,
  onKeep,
}: {
  item: NewsItem;
  /** The state to show, which may be ahead of the server's while a change is in flight. */
  kept: boolean;
  failed: boolean;
  onKeep(keep: boolean): void;
}) {
  return (
    <article className="rounded border border-border bg-panel px-3 py-2">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink">
            {item.url === null ? (
              item.title
            ) : (
              <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {item.title}
              </a>
            )}
          </p>
          {item.summary !== "" && <p className="mt-1 text-xs text-ink-muted">{item.summary}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
            <span>{item.publisher}</span>
            <span className="tabular-nums">
              {item.publishedAt === null
                ? "brak czasu publikacji"
                : formatInstant(Math.floor(item.publishedAt.getTime() / 1000))}
            </span>
            <span className="tabular-nums" title="opóźnienie: ile spóźnił się feed – ile czekaliśmy">
              opóźnienie {delayText(item)}
            </span>
            {!kept && item.expiresAt !== null && (
              <span>zniknie {item.expiresAt.toLocaleDateString("pl-PL")}</span>
            )}
          </div>
        </div>
        <button
          type="button"
          aria-pressed={kept}
          className={`shrink-0 rounded border px-2 py-0.5 text-xs ${
            kept ? "border-accent text-accent" : "border-border text-ink-muted"
          }`}
          onClick={() => onKeep(!kept)}
        >
          {kept ? "zachowany" : "zachowaj"}
        </button>
      </div>
      {failed && (
        <p role="alert" className="mt-1 text-xs text-critical">
          Nie udało się zmienić znacznika — stan sprzed kliknięcia.
        </p>
      )}
    </article>
  );
}
