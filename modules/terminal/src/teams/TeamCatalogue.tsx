import { useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import type { TeamsApi, TeamSummary } from "./teamsApi";

/**
 * The list an operator picks a team from — name, description and when it last changed,
 * which is exactly what the module's catalogue publishes and all of what this needs
 * (`terminal-teams`, "Katalog pokazuje, co jest do uruchomienia"; specs/teams-catalogue,
 * "lista powstaje bez pobierania definicji"). No definition is read here, so a catalogue
 * of twenty teams is one request.
 *
 * A run starts from here and a team is opened from here (`terminal-teams`, "z każdej
 * pozycji może otworzyć zespół albo uruchomić przebieg") — opening by double-click, since
 * that is the thing done to a row most often and it used to be a button among five. The
 * runs themselves are read in `TeamRunsView`, never here: a catalogue that listed every
 * team's runs would be one request per row.
 */
export function TeamCatalogue({
  teams,
  status,
  error,
  api,
  onOpen,
  onWatch,
  onRuns,
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
  /** The run just started, and the team it belongs to — the runs view opens on both. */
  onWatch(runId: number, teamId: number, teamName: string): void;
  /** The team's runs, as a view of their own. */
  onRuns(id: number, name: string): void;
  onNew(): void;
  onSchedules(id: number, name: string): void;
  onChanged(): void;
  onReload(): void;
}) {
  const [retiring, setRetiring] = useState<TeamSummary | null>(null);
  const [starting, setStarting] = useState<number | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function run(team: TeamSummary) {
    setStarting(team.id);
    setRefusal(null);
    try {
      // Straight into the runs view with this run selected: the module answers with the
      // run, not with its result, and what the operator asked for was to watch it.
      const started = await api.startRun(team.id, new AbortController().signal);
      onWatch(started.id, team.id, team.name);
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

      {status === "ready" && teams.length > 0 && (
        <p className="text-xs text-ink-faint">Double-click a team to open it.</p>
      )}

      <ul className="flex flex-col gap-2">
        {teams.map((team) => (
          <li
            key={team.id}
            // The way in, replacing the `Open` button that used to sit among four others —
            // opening a team is the one thing done to a row far more often than everything
            // else on it, and it had the same weight as `Retire`. `Enter` does the same for
            // a keyboard: a double-click is not reachable from one, and this row is the
            // only affordance left.
            tabIndex={0}
            onDoubleClick={() => onOpen(team.id)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              if (event.target !== event.currentTarget) return;
              onOpen(team.id);
            }}
            className="cursor-pointer rounded border border-border bg-panel px-3 py-2 focus-visible:border-primary-line focus-visible:outline-none"
          >
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
                {/* A door, not a drawer. This used to unfold the run list inside the row,
                    which meant picking a run took two clicks and then read the run on a
                    canvas that had to be opened separately. It now goes to the view where
                    the list and the picture of the run stand together. */}
                <button
                  type="button"
                  onClick={() => onRuns(team.id, team.name)}
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
                  onClick={() => setRetiring(team)}
                  className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink-muted hover:bg-panel-strong"
                >
                  Retire
                </button>
              </div>
            </div>
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
