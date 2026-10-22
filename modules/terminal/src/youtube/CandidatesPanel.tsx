import { useState } from "react";
import { messageOf, useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { CandidateChoiceDialog } from "./dialogs";
import { duration } from "./present";
import type {
  Candidate,
  CandidateDecision,
  CandidateSort,
  CandidateView,
  IgnoredChannel,
  YoutubeApi,
} from "./youtubeApi";

/**
 * What the topics found. A topic only proposes: nothing here is transcribed or read until the operator says so, which is what
 * the four actions are. The model's sentence is a hint about why a film may be worth the click, not a verdict on it — a film it
 * could not look at is offered all the same and says so.
 */

const POLL_MS = 60_000;
const NONE: Candidate[] = [];
const NO_CHANNELS: IgnoredChannel[] = [];

const VIEW_LABEL: Record<CandidateView, string> = {
  open: "Proponowane",
  rejected: "Odrzucone przez model",
  decided: "Z decyzją",
};
const SORT_LABEL: Record<CandidateSort, string> = { found: "Ostatnio znalezione", published: "Ostatnio opublikowane" };
const DECISION_LABEL: Record<CandidateDecision, string> = {
  dismissed: "odrzucony",
  analysed: "przekazany do analizy",
  channel_followed: "kanał obserwowany",
  channel_ignored: "kanał ignorowany",
};

type Asking =
  | { kind: "follow" | "analyse" | "ignore"; candidate: Candidate }
  | null;

export function CandidatesPanel({ client, onChanged }: { client: YoutubeApi; onChanged(): void }) {
  const [view, setView] = useState<CandidateView>("open");
  const [sort, setSort] = useState<CandidateSort>("found");
  const list = useRead<Candidate[]>({
    key: ["youtube", "candidates", view, sort],
    read: (signal) => client.candidates({ view, sort }, signal),
    initial: NONE,
    fallbackMessage: "nie udało się wczytać kandydatów",
    pollMs: POLL_MS,
  });
  const ignored = useRead<IgnoredChannel[]>({
    key: ["youtube", "ignored-channels"],
    read: (signal) => client.ignoredChannels(signal),
    initial: NO_CHANNELS,
    fallbackMessage: "nie udało się wczytać ignorowanych kanałów",
  });
  const [asking, setAsking] = useState<Asking>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // A second click on the same button would arrive after the first has decided, and be refused for it.
  const [busy, setBusy] = useState(false);

  const done = () => {
    list.reload();
    ignored.reload();
    onChanged();
  };

  async function attempt(work: () => Promise<void>, fallback: string) {
    setFailure(null);
    setBusy(true);
    try {
      await work();
      done();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, fallback));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <nav className="flex gap-1" aria-label="widok kandydatów">
          {(Object.keys(VIEW_LABEL) as CandidateView[]).map((id) => (
            <Button key={id} size="xs" tone={view === id ? "primary" : "muted"} aria-pressed={view === id} onClick={() => setView(id)}>
              {VIEW_LABEL[id]}
            </Button>
          ))}
        </nav>
        <nav className="flex gap-1" aria-label="kolejność">
          {(Object.keys(SORT_LABEL) as CandidateSort[]).map((id) => (
            <Button key={id} size="xs" tone={sort === id ? "primary" : "quiet"} aria-pressed={sort === id} onClick={() => setSort(id)}>
              {SORT_LABEL[id]}
            </Button>
          ))}
        </nav>
      </div>

      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      {failure !== null && <p className="text-sm text-critical">{failure}</p>}
      {list.status === "ready" && list.value.length === 0 && (
        <p className="text-sm text-ink-muted">
          {view === "open"
            ? "Nie ma kandydatów. Tematy szukają w swoim odstępie — nowe filmy pojawią się tu same."
            : "Nic na tej liście."}
        </p>
      )}

      <ul className="flex flex-col gap-1">
        {list.value.map((candidate) => (
          <CandidateRow
            key={candidate.videoId}
            candidate={candidate}
            busy={busy}
            onAsk={(kind) => setAsking({ kind, candidate })}
            onDismiss={() => void attempt(() => client.dismissCandidate(candidate.videoId, new AbortController().signal), "nie udało się odrzucić filmu")}
          />
        ))}
      </ul>

      {ignored.value.length > 0 && (
        <details className="rounded border border-border bg-panel px-3 py-2">
          <summary className="cursor-pointer text-xs text-ink-muted">Ignorowane kanały ({ignored.value.length})</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {ignored.value.map((channel) => (
              <li key={channel.channelId} className="flex items-center gap-3 text-sm text-ink">
                <span className="min-w-0 flex-1">{channel.title}</span>
                <Button
                  size="xs"
                  tone="muted"
                  onClick={() =>
                    void attempt(() => client.unignoreChannel(channel.channelId, new AbortController().signal), "nie udało się cofnąć ignorowania")
                  }
                >
                  Cofnij
                </Button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {asking?.kind === "follow" && (
        <CandidateChoiceDialog
          client={client}
          title="Obserwuj kanał"
          confirmLabel="Obserwuj"
          busyLabel="Pytam YouTube…"
          onConfirm={(promptId) =>
            client.followCandidateChannel(asking.candidate.videoId, promptId, new AbortController().signal).then(() => undefined)
          }
          onClose={() => setAsking(null)}
          onDone={done}
          choosing="Prompt, którym czytane są nowe filmy kanału"
        >
          <span className="text-ink">{asking.candidate.channelTitle}</span> trafi na listę kanałów, a inne propozycje z tego
          kanału znikną z tej listy.
        </CandidateChoiceDialog>
      )}
      {asking?.kind === "analyse" && (
        <CandidateChoiceDialog
          client={client}
          title="Przeanalizuj film"
          confirmLabel="Dodaj do kolejki"
          busyLabel="Pytam YouTube…"
          onConfirm={(promptId) =>
            client.analyseCandidate(asking.candidate.videoId, promptId, new AbortController().signal).then(() => undefined)
          }
          onClose={() => setAsking(null)}
          onDone={done}
          choosing="Prompt, którym film zostanie przeczytany"
        >
          <span className="text-ink">{asking.candidate.title}</span> zostanie przepisany i przeczytany od razu. Kosztuje jednostkę
          limitu źródła, minuty słuchania modelu i tokeny; nie wysyła powiadomienia.
        </CandidateChoiceDialog>
      )}
      {asking?.kind === "ignore" && (
        <ConfirmDialog
          title="Ignoruj kanał"
          confirmLabel="Ignoruj"
          busyLabel="Zapisuję…"
          fallbackError="nie udało się zignorować kanału"
          onConfirm={async () => {
            await client.ignoreCandidateChannel(asking.candidate.videoId, new AbortController().signal);
            done();
          }}
          onClose={() => setAsking(null)}
        >
          <p className="text-xs text-ink-secondary">
            Filmy kanału <span className="text-ink">{asking.candidate.channelTitle}</span> przestaną być proponowane, a te,
            które już są na liście, znikną z niej. Można to cofnąć poniżej listy.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

function CandidateRow({
  candidate,
  busy,
  onAsk,
  onDismiss,
}: {
  candidate: Candidate;
  busy: boolean;
  onAsk(kind: "follow" | "analyse" | "ignore"): void;
  onDismiss(): void;
}) {
  const length = duration(candidate.durationSeconds);
  const open = candidate.decision === null;
  return (
    <li className="flex flex-col gap-1 rounded border border-border bg-panel px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <a
          href={candidate.url}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-ink underline decoration-border hover:decoration-ink"
        >
          {candidate.title}
        </a>
        {candidate.simulated && (
          <span className="rounded bg-warning-soft px-1 text-[11px] font-semibold text-warning">SYMULACJA</span>
        )}
        {candidate.verdict === "unscreened" && (
          <span className="rounded bg-raised px-1 text-[11px] text-ink-muted" title="żaden model nie obejrzał metadanych">
            nieprzesiany
          </span>
        )}
        {candidate.verdict === "rejected" && (
          <span className="rounded bg-raised px-1 text-[11px] text-ink-muted">odrzucony przez model</span>
        )}
        {candidate.decision !== null && (
          <span className="rounded bg-raised px-1 text-[11px] text-ink-muted">{DECISION_LABEL[candidate.decision]}</span>
        )}
      </div>
      <span className="text-xs text-ink-faint">
        {candidate.channelTitle}
        {length !== null && ` · ${length}`} · temat: {candidate.topic} · opublikowany{" "}
        {candidate.publishedAt.toLocaleString("pl-PL")} · znaleziony {candidate.foundAt.toLocaleString("pl-PL")}
      </span>
      {candidate.reason !== null && <span className="text-xs italic text-ink-secondary">{candidate.reason}</span>}
      {open && (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button size="xs" tone="primary" onClick={() => onAsk("follow")} disabled={candidate.channelId === null}>
            Obserwuj kanał
          </Button>
          <Button size="xs" tone="muted" onClick={() => onAsk("analyse")}>
            Analizuj film
          </Button>
          <Button size="xs" tone="muted" onClick={onDismiss} disabled={busy}>
            Odrzuć
          </Button>
          <Button size="xs" tone="critical" onClick={() => onAsk("ignore")} disabled={candidate.channelId === null}>
            Ignoruj kanał
          </Button>
        </div>
      )}
    </li>
  );
}
