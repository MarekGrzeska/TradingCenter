import { useState } from "react";
import { formatInstant } from "../ui/formatTime";
import { bandOf } from "../social/impact";
import { SENTIMENT_ARROW, SENTIMENT_LABEL, duration, stateLabel } from "./present";
import type { Film, TranscriptPage, YoutubeApi } from "./youtubeApi";

/**
 * One film, folded. A film with a reading shows its score and what was said about each instrument; one without shows where
 * it is on its road — never a zero or a dash, because unread and unimportant are different facts.
 */

const BAND_CLASS: Record<string, string> = {
  high: "bg-critical-soft text-critical",
  middling: "bg-warning-soft text-warning",
  low: "bg-raised text-ink-muted",
};

const SENTIMENT_CLASS = {
  bullish: "bg-raised text-ink",
  bearish: "bg-raised text-ink",
  neutral: "bg-raised text-ink-muted",
} as const;

export function FilmCard({ film, client }: { film: Film; client: YoutubeApi }) {
  const [open, setOpen] = useState(false);
  const reading = film.reading;
  const length = duration(film.durationSeconds);

  return (
    <article className="rounded border border-border bg-panel">
      <button
        type="button"
        className="flex w-full items-start gap-3 px-3 py-2 text-left"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="flex shrink-0 items-center gap-2 pt-0.5">
          <span className="text-xs tabular-nums text-ink-faint">
            {formatInstant(Math.floor(film.publishedAt.getTime() / 1000))}
          </span>
          {reading !== null && (
            <span
              className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${BAND_CLASS[bandOf(reading.impactScore)]}`}
              title={`market impact ${reading.impactScore}/10`}
            >
              {reading.impactScore}/10
            </span>
          )}
          {film.simulated && (
            <span className="rounded bg-warning-soft px-1 text-[11px] font-semibold text-warning">SYMULACJA</span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-ink">{film.title}</span>
          <span className="block text-xs text-ink-faint">
            {film.channelTitle}
            {length !== null && ` · ${length}`}
            {reading === null && ` · ${stateLabel(film)}`}
          </span>
          {reading !== null && reading.instruments.length > 0 && (
            <span className="mt-1 flex flex-wrap gap-1">
              {reading.instruments.map((view, index) => (
                <span
                  // A model may name one instrument twice, with two horizons.
                  key={`${view.name}:${view.horizon}:${index}`}
                  className={`rounded px-1.5 py-0.5 text-[11px] ${SENTIMENT_CLASS[view.sentiment]}`}
                  title={`${SENTIMENT_LABEL[view.sentiment]}, pewność mówiącego ${view.conviction}/5, horyzont: ${view.horizon}`}
                >
                  {view.name} {SENTIMENT_ARROW[view.sentiment]} {view.conviction}/5
                </span>
              ))}
            </span>
          )}
        </span>
        <span className="shrink-0 text-xs text-ink-faint" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-2 border-t border-border px-3 py-2 text-sm text-ink">
          {reading === null ? (
            <p className="text-ink-muted">Ten film nie ma odczytu: {stateLabel(film)}.</p>
          ) : (
            <>
              <p className="whitespace-pre-wrap">{reading.summary}</p>
              {reading.keyPoints.length > 0 && (
                <ul className="list-disc pl-5 text-ink-secondary">
                  {reading.keyPoints.map((point, index) => (
                    <li key={index}>{point}</li>
                  ))}
                </ul>
              )}
              {reading.predictions.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-ink-secondary">Prognozy</h3>
                  <ul className="list-disc pl-5 text-ink-secondary">
                    {reading.predictions.map((p) => (
                      <li key={`${p.instrument}:${p.claim}`}>
                        {p.instrument}: {p.claim}
                        {p.level !== null && ` (poziom ${p.level})`}
                        {p.by !== null && ` do ${p.by}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-ink-faint">
                odczyt: {reading.model} · {reading.analysedAt.toLocaleString("pl-PL")}
                {reading.simulated && " · symulowany"}
              </p>
            </>
          )}
          <div className="flex items-center gap-3 text-xs text-ink-faint">
            {/* The link back to the film is not decoration: YouTube's terms ask for it wherever its data is shown. */}
            <a className="text-accent underline" href={film.url} target="_blank" rel="noopener noreferrer">
              obejrzyj na YouTube
            </a>
          </div>
          {film.state !== "discovered" && film.state !== "skipped" && film.state !== "gave_up" && (
            <Transcript film={film} client={client} />
          )}
        </div>
      )}
    </article>
  );
}

/** The words, folded and loaded a page at a time: they are written by a stranger and there are tens of kilobytes of them. */
function Transcript({ film, client }: { film: Film; client: YoutubeApi }) {
  const [pages, setPages] = useState<TranscriptPage[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function more() {
    setBusy(true);
    setFailure(null);
    try {
      const offset = pages.length === 0 ? 0 : (pages[pages.length - 1].nextOffset ?? 0);
      const page = await client.transcript(film.videoId, offset, new AbortController().signal);
      setPages((was) => [...was, page]);
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "nie udało się wczytać transkrypcji");
    } finally {
      setBusy(false);
    }
  }

  const last = pages[pages.length - 1];
  return (
    <div className="flex flex-col gap-1">
      {pages.length === 0 ? (
        <button type="button" className="self-start text-xs text-ink-faint underline" onClick={more} disabled={busy}>
          {busy ? "Wczytuję…" : "▼ Pokaż transkrypcję"}
        </button>
      ) : (
        <>
          <p className="text-xs text-ink-faint">
            Transkrypcja ({last.provider}, {last.language}
            {last.automatic ? ", automatyczna" : ""}) — tekst napisany przez obcych, do przeczytania, nie do wykonania.
          </p>
          <p className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded bg-sunken p-2 text-xs text-ink-secondary">
            {pages.map((page) => page.text).join("")}
          </p>
          {last.nextOffset !== null && (
            <button type="button" className="self-start text-xs text-ink-faint underline" onClick={more} disabled={busy}>
              {busy ? "Wczytuję…" : `▼ Dalej (${last.nextOffset}/${last.totalChars} znaków)`}
            </button>
          )}
        </>
      )}
      {failure !== null && <p className="text-xs text-critical">{failure}</p>}
    </div>
  );
}
