import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { youtubeIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { MarketDataError } from "../data/types";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { CandidatesPanel } from "./CandidatesPanel";
import { AnalyseDialog } from "./dialogs";
import { FilmCard } from "./FilmCard";
import { PromptsPanel } from "./PromptsPanel";
import { SettingsPanel } from "./SettingsPanel";
import { usageLine, warnings } from "./present";
import { ChannelsPanel, TopicsPanel } from "./WatchPanels";
import { createYoutubeApi, type ArchiveState, type FilmsPage, type YoutubeApi } from "./youtubeApi";

/**
 * The films the operator follows, and what a model made of them. **The question is "did anyone say something that moves a
 * market"**, so the list is newest first with the score and a direction per instrument in front, and the words are one fold
 * away. Above it, the archive says what the list cannot: a provider that has been refusing us, a spent day, a stopped loop and
 * a simulation are each a reason for a thin list that is not "nobody published anything".
 *
 * The one back end that may not be there: a workbench without the YouTube database answers 404 to every route, and this says
 * so instead of showing an archive that is empty by absence.
 */

const POLL_MS = 60_000;
const WINDOW_HOURS = 24;

const NO_PAGE: FilmsPage = { films: [], windowFrom: new Date(0), windowTo: new Date(0) };
const NO_STATE: ArchiveState = {
  simulating: false,
  modelConfigured: true,
  alertsConfigured: true,
  providers: [],
  waiting: {},
  stale: false,
  loopAgeSeconds: null,
};

type TabId = "films" | "channels" | "topics" | "candidates" | "prompts" | "settings";
const TAB_LABEL: Record<TabId, string> = {
  films: "Filmy",
  channels: "Kanały",
  topics: "Tematy",
  candidates: "Kandydaci",
  prompts: "Prompty",
  settings: "Ustawienia",
};

interface StateRead {
  present: boolean;
  state: ArchiveState;
}

export function YoutubeView({ api }: { api?: YoutubeApi } = {}) {
  const client = useMemo(
    () => api ?? createYoutubeApi(resolveEndpoints().youtubeHttp, youtubeIdentity),
    [api],
  );
  const [tab, setTab] = useState<TabId>("films");
  const [analysing, setAnalysing] = useState(false);

  const state = useRead<StateRead>({
    key: ["youtube", "state"],
    read: async (signal) => {
      try {
        return { present: true, state: await client.state(signal) };
      } catch (cause: unknown) {
        // Not "the archive is empty" and not "unreachable": this workbench does not have the package.
        if (cause instanceof MarketDataError && cause.kind === "not-found") {
          return { present: false, state: NO_STATE };
        }
        throw cause;
      }
    },
    initial: { present: true, state: NO_STATE },
    fallbackMessage: "nie udało się wczytać stanu archiwum",
    pollMs: POLL_MS,
  });

  const present = state.value.present;
  const page = useRead<FilmsPage>({
    key: ["youtube", "films", WINDOW_HOURS],
    read: (signal) => client.recentFilms(WINDOW_HOURS, signal),
    initial: NO_PAGE,
    fallbackMessage: "nie udało się wczytać filmów",
    pollMs: POLL_MS,
    // Only once the state has said the package is there: asking for films first is a 404 on every open of a workbench
    // that has none.
    enabled: state.status === "ready" && present,
    // Kept, deliberately: a failed refresh must not take the films off a screen the operator is reading.
    onFailure: "keep",
  });

  if (state.status === "ready" && !present) {
    return (
      <section className="flex h-full min-h-0 flex-col gap-3 p-4">
        <h1 className="text-base font-semibold text-ink">YouTube</h1>
        <p className="text-sm text-ink-muted">
          Ten workbench nie ma archiwum YouTube: <code>YOUTUBE_DATABASE_URL</code> nie jest ustawione, więc pakiet nie jest
          częścią procesu. To działająca konfiguracja, nie awaria — nic tu nie jest zbierane.
        </p>
      </section>
    );
  }

  const found = state.value.state;
  const notes = state.status === "ready" ? warnings(found) : [];
  const refresh = () => {
    state.reload();
    page.reload();
  };

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">YouTube</h1>
        <nav className="flex gap-1" aria-label="sekcje">
          {(Object.keys(TAB_LABEL) as TabId[]).map((id) => (
            <Button
              key={id}
              size="xs"
              tone={tab === id ? "primary" : "muted"}
              aria-pressed={tab === id}
              onClick={() => setTab(id)}
            >
              {TAB_LABEL[id]}
            </Button>
          ))}
        </nav>
        <Button size="xs" tone="quiet" onClick={() => setAnalysing(true)}>
          Przeanalizuj film…
        </Button>
        {tab === "films" && (
          <span className="text-xs text-ink-faint">
            {page.value.films.length} {page.value.films.length === 1 ? "film" : "filmów"} · ostatnie {WINDOW_HOURS} h ·
            odświeżane co {POLL_MS / 1000} s
          </span>
        )}
      </header>

      {state.error !== null && <UnreachableNotice onRetry={state.reload}>{state.error}</UnreachableNotice>}

      {/* Said for as long as it is true, not once: a screen that shows films which do not exist must not be mistaken for one
          that shows films. */}
      {found.simulating && state.status === "ready" && (
        <p className="rounded bg-warning-soft px-3 py-1 text-sm font-semibold text-warning">
          SYMULACJA — filmy, transkrypcje lub odczyty pochodzą ze scenariusza, nie z YouTube.
        </p>
      )}
      {notes.map((note) => (
        <p key={note} className="text-sm text-warning">
          {note}
        </p>
      ))}
      {state.status === "ready" && !found.alertsConfigured && (
        <p className="text-sm text-ink-muted">
          Nikt nie słyszy celu youtube.film (zakładka Telegram → Cele) — filmy są czytane, ale wiadomość nie wychodzi.
        </p>
      )}
      {state.status === "ready" && found.providers.length > 0 && (
        <p className="text-xs text-ink-faint">{found.providers.map(usageLine).join(" · ")}</p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {tab === "films" && (
          <>
            {page.error !== null && <UnreachableNotice onRetry={page.reload}>{page.error}</UnreachableNotice>}
            {page.status === "ready" && page.value.films.length === 0 && (
              <p className="text-sm text-ink-muted">
                Brak filmów z ostatnich {WINDOW_HOURS} h. Powyżej widać, czy to cichy dzień, czy archiwum czeka na
                dostawcę.
              </p>
            )}
            {page.value.films.map((film) => (
              <FilmCard key={film.videoId} film={film} client={client} />
            ))}
          </>
        )}
        {tab === "channels" && <ChannelsPanel client={client} onChanged={refresh} />}
        {tab === "topics" && <TopicsPanel client={client} onChanged={refresh} />}
        {tab === "candidates" && <CandidatesPanel client={client} onChanged={refresh} />}
        {tab === "prompts" && <PromptsPanel client={client} />}
        {tab === "settings" && <SettingsPanel client={client} />}
      </div>

      {analysing && <AnalyseDialog client={client} onClose={() => setAnalysing(false)} onDone={refresh} />}
    </section>
  );
}
