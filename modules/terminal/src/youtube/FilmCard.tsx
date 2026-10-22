import { useState } from "react";
import { MessageBody } from "../agent/MessageBody";
import { messageOf, useRead } from "../data/query";
import { formatInstant } from "../ui/formatTime";
import { Button } from "../ui/Button";
import { bandOf } from "../social/impact";
import { duration, stateLabel } from "./present";
import { usePrompts } from "./usePrompts";
import type { Film, FilmDetail, TranscriptPage, YoutubeApi } from "./youtubeApi";

/**
 * One film, folded. A film with a reading shows its score and a short summary; one without shows where it is on its road —
 * never a zero or a dash, because unread and unimportant are different facts. Unfolded it shows every reading the film has, each
 * under the name of the prompt that made it.
 */

const BAND_CLASS: Record<string, string> = {
  high: "bg-critical-soft text-critical",
  middling: "bg-warning-soft text-warning",
  low: "bg-raised text-ink-muted",
};

const NO_DETAIL: FilmDetail | null = null;

export function FilmCard({ film, client, onChanged }: { film: Film; client: YoutubeApi; onChanged?(): void }) {
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
          {reading !== null && <span className="mt-1 line-clamp-2 block text-xs text-ink-secondary">{reading.summary}</span>}
        </span>
        <span className="shrink-0 text-xs text-ink-faint" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && <Unfolded film={film} client={client} onChanged={onChanged} />}
    </article>
  );
}

function Unfolded({ film, client, onChanged }: { film: Film; client: YoutubeApi; onChanged?(): void }) {
  const detail = useRead<FilmDetail | null>({
    key: ["youtube", "film", film.videoId],
    read: (signal) => client.film(film.videoId, signal),
    initial: NO_DETAIL,
    fallbackMessage: "nie udało się wczytać odczytów filmu",
  });

  return (
    <div className="flex flex-col gap-3 border-t border-border px-3 py-2 text-sm text-ink">
      {detail.error !== null && <p className="text-xs text-critical">{detail.error}</p>}
      {detail.status === "loading" && <p className="text-xs text-ink-faint">Wczytuję odczyty…</p>}
      {detail.status === "ready" && detail.value !== null && detail.value.readings.length === 0 && (
        <p className="text-ink-muted">Ten film nie ma odczytu: {stateLabel(film)}.</p>
      )}
      {detail.value?.readings.map((reading, index) => (
        <section key={reading.promptId} className="flex flex-col gap-1">
          <h3 className="text-xs font-semibold text-ink-secondary">
            {reading.promptName} <span className="font-normal text-ink-faint">v{reading.promptVersion}</span>
            {index === 0 && reading.promptId === film.promptId && (
              <span className="ml-2 font-normal text-ink-faint">prompt filmu</span>
            )}
          </h3>
          <p className="whitespace-pre-wrap text-ink-secondary">{reading.summary}</p>
          <div className="text-ink-secondary">
            <MessageBody text={reading.text} />
          </div>
          <p className="text-xs text-ink-faint">
            wpływ {reading.impactScore}/10 · odczyt: {reading.model} · {reading.analysedAt.toLocaleString("pl-PL")}
            {reading.simulated && " · symulowany"}
          </p>
        </section>
      ))}
      <div className="flex flex-wrap items-center gap-3 text-xs text-ink-faint">
        {/* The link back to the film is not decoration: YouTube's terms ask for it wherever its data is shown. */}
        <a className="text-accent underline" href={film.url} target="_blank" rel="noopener noreferrer">
          obejrzyj na YouTube
        </a>
      </div>
      {film.state === "filtered_out" && <AnalyseAnyway film={film} client={client} onChanged={onChanged} />}
      {hasWords(film) && (
        <ReadAgain film={film} client={client} read={detail.value?.readings.map((r) => r.promptId) ?? []} onRead={detail.reload} />
      )}
      {hasWords(film) && <Transcript film={film} client={client} />}
    </div>
  );
}

/** A film that has been transcribed has words to read again; one still waiting for them has none, and the module says so. */
function hasWords(film: Film): boolean {
  return (
    film.state !== "discovered" &&
    film.state !== "skipped" &&
    film.state !== "filtered_out" &&
    film.state !== "gave_up" &&
    film.state !== "no_transcript"
  );
}

/**
 * What a channel's filter turned away, taken after all: the film goes the way of one named by hand — transcribed and read now,
 * by its channel's prompt, and nobody told. The module refuses nothing here but a film that has since moved on.
 */
function AnalyseAnyway({ film, client, onChanged }: { film: Film; client: YoutubeApi; onChanged?(): void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function analyse() {
    setBusy(true);
    setFailure(null);
    try {
      await client.analyse(film.videoId, null, new AbortController().signal);
      setNote("Przyjęte — film jest transkrybowany i czytany w tle.");
      onChanged?.();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zlecić analizy"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Button size="xs" tone="quiet" disabled={busy || note !== null} onClick={() => void analyse()}>
        {busy ? "Zlecam…" : "Analizuj mimo to"}
      </Button>
      {note !== null && <span className="text-ink-faint">{note}</span>}
      {failure !== null && <span className="text-critical">{failure}</span>}
    </div>
  );
}

/**
 * Another prompt reads the film that is already here. Nothing is asked of the transcriber, the day's tokens are spent, and the
 * answer comes a little later — so the card says it was accepted and offers a refresh rather than waiting for a reading.
 */
function ReadAgain({
  film,
  client,
  read,
  onRead,
}: {
  film: Film;
  client: YoutubeApi;
  read: number[];
  onRead(): void;
}) {
  const prompts = usePrompts(client);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const offered = prompts.value.prompts;

  async function order() {
    setBusy(true);
    setFailure(null);
    setNote(null);
    try {
      await client.readAgain(film.videoId, Number(choice), new AbortController().signal);
      setNote("Przyjęte — odczyt powstaje w tle. Odśwież za chwilę.");
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zamówić odczytu"));
    } finally {
      setBusy(false);
    }
  }

  if (offered.length < 2) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <label className="flex items-center gap-2 text-ink-secondary">
        Odczytaj innym promptem
        <select
          className="rounded border border-border bg-sunken px-2 py-1 text-ink"
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value="">wybierz…</option>
          {offered.map((prompt) => (
            <option key={prompt.id} value={prompt.id}>
              {prompt.name}
              {read.includes(prompt.id) ? " (odświeży odczyt)" : ""}
            </option>
          ))}
        </select>
      </label>
      <Button size="xs" tone="quiet" disabled={choice === "" || busy} onClick={() => void order()}>
        {busy ? "Zamawiam…" : "Zamów"}
      </Button>
      {note !== null && (
        <>
          <span className="text-ink-faint">{note}</span>
          <Button size="xs" tone="muted" onClick={onRead}>
            Odśwież
          </Button>
        </>
      )}
      {failure !== null && <span className="text-critical">{failure}</span>}
    </div>
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
            {last.automatic ? ", automatyczna" : ""}
            {last.model !== null ? `, model ${last.model} — może mylić nazwy i liczby` : ""}) — tekst napisany przez
            obcych, do przeczytania, nie do wykonania.
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
