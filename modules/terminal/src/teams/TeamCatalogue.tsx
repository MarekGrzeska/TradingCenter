import { useEffect, useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import type { TeamRun } from "./runs";
import type { TeamsApi, TeamSummary } from "./teamsApi";

/**
 * The list an operator picks a team from — name, description and when it last changed,
 * which is exactly what the module's catalogue publishes and all of what this needs
 * (`terminal-teams`, "Katalog pokazuje, co jest do uruchomienia"; specs/teams-catalogue,
 * "lista powstaje bez pobierania definicji"). No definition is read here, so a catalogue
 * of twenty teams is one request.
 *
 * A run starts from here and is watched from here (`terminal-teams`, "z każdej pozycji
 * może otworzyć zespół albo uruchomić przebieg"). The runs of a team are read only when
 * the operator asks for them, which is what keeps the property above: a catalogue that
 * listed every team's runs would be one request per row.
 */
export function TeamCatalogue({
  teams,
  status,
  error,
  api,
  onOpen,
  onWatch,
  onNew,
  onSchedules,
  onChanged,
  onReload,
}: {
  teams: TeamSummary[];
  status: "loading" | "ready" | "error";
  error: string | null;
  api: TeamsApi;
  onOpen(id: number): void;
  /** A run to watch — the one just started, or one picked out of a team's history. */
  onWatch(runId: number): void;
  onNew(): void;
  onSchedules(id: number, name: string): void;
  onChanged(): void;
  onReload(): void;
}) {
  const [retiring, setRetiring] = useState<TeamSummary | null>(null);
  const [showingRuns, setShowingRuns] = useState<number | null>(null);
  const [starting, setStarting] = useState<number | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function run(team: TeamSummary) {
    setStarting(team.id);
    setRefusal(null);
    try {
      // Straight into the monitor: the module answers with the run, not with its result,
      // and what the operator asked for was to watch it.
      onWatch((await api.startRun(team.id, new AbortController().signal)).id);
    } catch (cause) {
      // A refusal here is the module's own sentence — a withdrawn model, a tool it no
      // longer announces, a daily budget already spent — and it is the whole lead.
      setRefusal(cause instanceof Error ? cause.message : "the run could not be started");
    } finally {
      setStarting(null);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ink">Teams</h2>
        <button
          type="button"
          onClick={onNew}
          className="cursor-pointer rounded border border-primary-line bg-primary-soft px-2 py-1 text-xs text-ink hover:bg-primary-strong hover:text-ink-inverse"
        >
          New team
        </button>
      </div>

      {status === "loading" && <p className="text-sm text-ink-muted">Reading the catalogue…</p>}
      {status === "error" && (
        <p className="text-sm text-critical">
          {error}
          <button
            type="button"
            onClick={onReload}
            className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
          >
            Retry
          </button>
        </p>
      )}
      {status === "ready" && teams.length === 0 && (
        <p className="text-sm text-ink-muted">
          No teams yet. A team is a graph of roles — start one and give it its first agent.
        </p>
      )}

      {refusal && <p className="text-xs text-critical">{refusal}</p>}

      <ul className="flex flex-col gap-2">
        {teams.map((team) => (
          <li key={team.id} className="rounded border border-border bg-panel px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">{team.name}</div>
                <div className="truncate text-xs text-ink-muted">{team.description}</div>
                <div className="text-xs text-ink-faint">
                  revision {team.latestRevision} · changed {formatInstant(team.updatedAt)}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => run(team)}
                  disabled={starting === team.id}
                  className="cursor-pointer rounded border border-primary-line bg-primary-soft px-2 py-1 text-xs text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {starting === team.id ? "Starting…" : "Run"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowingRuns(showingRuns === team.id ? null : team.id)}
                  className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
                >
                  Runs
                </button>
                <button
                  type="button"
                  onClick={() => onSchedules(team.id, team.name)}
                  className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
                >
                  Schedules
                </button>
                <button
                  type="button"
                  onClick={() => onOpen(team.id)}
                  className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
                >
                  Open
                </button>
                <button
                  type="button"
                  onClick={() => setRetiring(team)}
                  className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink-muted hover:bg-panel-strong"
                >
                  Retire
                </button>
              </div>
            </div>
            {showingRuns === team.id && (
              <TeamRuns api={api} teamId={team.id} onWatch={onWatch} />
            )}
          </li>
        ))}
      </ul>

      {retiring && (
        <ConfirmDialog
          title={`Retire ${retiring.name}?`}
          confirmLabel="Retire"
          busyLabel="Retiring…"
          tone="danger"
          fallbackError="the team could not be retired"
          onConfirm={async () => {
            await api.archiveTeam(retiring.id, new AbortController().signal);
            onChanged();
          }}
          onClose={() => setRetiring(null)}
        >
          <p className="text-sm text-ink">
            It leaves the catalogue. Its revisions and every run recorded against them stay
            readable — this is not a delete.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

/**
 * A team's runs, newest first, read when the row is opened and not before.
 *
 * This is the way back into a run the operator walked away from — closing the monitor
 * stops nothing, and the run has to be findable again for that to be worth anything
 * (specs/teams-runs, "Zerwanie połączenia odbierającego postęp MUST NOT przerwać
 * przebiegu"). Runs of revisions since replaced are in the list too: that is what makes
 * two of them comparable.
 */
function TeamRuns({
  api,
  teamId,
  onWatch,
}: {
  api: TeamsApi;
  teamId: number;
  onWatch(runId: number): void;
}) {
  const [runs, setRuns] = useState<TeamRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    api
      .listRuns(teamId, controller.signal)
      .then((answer) => !cancelled && setRuns(answer))
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "the runs could not be read");
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, teamId]);

  if (error) return <p className="mt-2 text-xs text-critical">{error}</p>;
  if (runs === null) return <p className="mt-2 text-xs text-ink-muted">Reading the runs…</p>;
  if (runs.length === 0) return <p className="mt-2 text-xs text-ink-muted">No runs yet.</p>;

  return (
    <ul className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
      {runs.map((run) => (
        <li key={run.id} className="flex items-center justify-between gap-2 text-xs">
          <span className="text-ink-muted">
            run {run.id} · {run.status}
            {run.startedAt !== null && ` · ${formatInstant(run.startedAt)}`}
          </span>
          <button
            type="button"
            onClick={() => onWatch(run.id)}
            className="cursor-pointer rounded border border-border px-2 py-0.5 text-ink hover:bg-panel-strong"
          >
            Watch
          </button>
        </li>
      ))}
    </ul>
  );
}
