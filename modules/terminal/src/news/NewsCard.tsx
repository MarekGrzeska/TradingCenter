import { useState } from "react";
import { formatInstant } from "../ui/formatTime";
import { delayText, expiryText } from "./delay";
import type { NewsItem } from "./newsApi";

/**
 * One headline: the feed's own words, when it said them, how late that reached us, and whether to keep it.
 * A click opens the whole of it here — the operator reads it in the app, not on somebody else's page.
 */

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
  const [open, setOpen] = useState(false);
  const body = item.content !== "" ? item.content : item.summary;
  const expiry = expiryText(item.expiresAt, new Date());

  return (
    <article className="rounded border border-border bg-panel">
      <div className="flex items-start gap-3 px-3 py-2">
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
        >
          <span className="block text-sm text-ink">{item.title}</span>
          {!open && item.summary !== "" && (
            <span className="mt-1 line-clamp-2 block text-xs text-ink-muted">{item.summary}</span>
          )}
          <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
            <span>{item.publisher}</span>
            <span className="tabular-nums">
              {item.publishedAt === null
                ? "brak czasu publikacji"
                : formatInstant(Math.floor(item.publishedAt.getTime() / 1000))}
            </span>
            <span className="tabular-nums" title="opóźnienie: ile spóźnił się feed – ile czekaliśmy">
              opóźnienie {delayText(item)}
            </span>
            {!kept && expiry !== null && <span>{expiry}</span>}
            <span aria-hidden>{open ? "▲" : "▼"}</span>
          </span>
        </button>
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

      {open && (
        <div className="border-t border-border px-3 py-2">
          {body !== "" && <p className="whitespace-pre-wrap text-sm text-ink">{body}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-faint">
            {item.content === "" && (
              <span>Feed niesie tylko zajawkę — pełny tekst jest u źródła.</span>
            )}
            {item.url !== null && (
              <a
                className="text-accent underline"
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                otwórz oryginał
              </a>
            )}
          </p>
        </div>
      )}

      {failed && (
        <p role="alert" className="px-3 pb-2 text-xs text-critical">
          Nie udało się zmienić znacznika — stan sprzed kliknięcia.
        </p>
      )}
    </article>
  );
}
