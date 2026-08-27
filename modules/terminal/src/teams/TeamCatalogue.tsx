import { useState } from "react";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import type { TeamsApi, TeamSummary } from "./teamsApi";

/**
 * Name, description and when it last changed — what the module's catalogue publishes, so twenty teams are one
 * request and no definition is read. The runs are read in `TeamRunsView`: listing them here is a request a row.
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
  onMemory,
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
  onMemory(id: number, name: string): void;
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
        <Button
          tone="primary"
          onClick={onNew}
        >
          New team
        </Button>
      </div>

      {status === "loading" && <p className="text-sm text-ink-muted">Reading the catalogue…</p>}
      {status === "error" && (
        <UnreachableNotice onRetry={onReload}>{error}</UnreachableNotice>
      )}
      {status === "ready" && teams.length === 0 && (
        <p className="text-sm text-ink-muted">
          No teams yet. A team is a graph of roles — start one and give it its first agent.
        </p>
      )}

      {refusal && <p className="text-xs text-critical">{refusal}</p>}

      {status === "ready" && teams.length > 0 && (
        <p className="text-xs text-ink-faint">Click a team to open it.</p>
      )}

      <ul className="flex flex-col gap-2">
        {teams.map((team) => (
          <li
            key={team.id}
            // The way in, replacing the `Open` button that had the same weight as `Retire` — opening a team
            // is done far more often than anything else on the row. `Enter` does the same for a keyboard.
            tabIndex={0}
            title="Click to open"
            // A single click, and the guard makes that safe: the row carries four buttons, and a click that
            // started on one is that button's. `closest` because a button's own text node is what is hit.
            onClick={(event) => {
              if (event.target instanceof Element && event.target.closest("button")) return;
              onOpen(team.id);
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              if (event.target !== event.currentTarget) return;
              onOpen(team.id);
            }}
            // `group` so the row's hover lights the hint beside the name. Border and ground both move: on a
            // row that also carries four buttons, the whole row has to read as the target.
            className="group cursor-pointer rounded border border-border bg-panel px-3 py-2 transition-colors hover:border-primary-line hover:bg-panel-strong focus-visible:border-primary-line focus-visible:outline-none"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="truncate text-sm text-ink">{team.name}</span>
                  {/* Says what the row does, at the moment the pointer is on it. Present in
                      the markup rather than mounted on hover, so nothing shifts as it
                      appears and a keyboard focus can show it too. */}
                  <span className="shrink-0 text-xs text-ink-faint opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                    click to open
                  </span>
                </div>
                <div className="truncate text-xs text-ink-muted">{team.description}</div>
                <div className="text-xs text-ink-faint">
                  revision {team.latestRevision} · changed {formatInstant(team.updatedAt)}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  tone="primary"
                  onClick={() => run(team)}
                  disabled={starting === team.id}
                >
                  {starting === team.id ? "Starting…" : "Run"}
                </Button>
                {/* A door, not a drawer. This used to unfold the run list inside the row,
                    which meant picking a run took two clicks and then read the run on a
                    canvas that had to be opened separately. It now goes to the view where
                    the list and the picture of the run stand together. */}
                <Button onClick={() => onRuns(team.id, team.name)}>
                  Runs
                </Button>
                <Button onClick={() => onSchedules(team.id, team.name)}>
                  Schedules
                </Button>
                <Button onClick={() => onMemory(team.id, team.name)}>
                  Memory
                </Button>
                <Button
                  tone="muted"
                  onClick={() => setRetiring(team)}
                >
                  Retire
                </Button>
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
