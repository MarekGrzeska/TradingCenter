import { useEffect, useState } from "react";
import { useAgentTurns } from "../agent/useAgentTurns";
import { formatInstant } from "../ui/formatTime";
import { RunMonitor } from "./RunMonitor";
import type { TeamRun } from "./runs";
import type { TeamsApi, TeamsModel } from "./teamsApi";

/**
 * One team's runs: the list, and the run picked out of it drawn underneath.
 *
 * This replaces a drawer that unfolded inside the catalogue row. That shape cost two clicks
 * to reach a run — open the drawer, then `Watch` — and then took the operator somewhere
 * else entirely to look at it, so comparing two runs meant walking back through the
 * catalogue each time. Here the list stays on screen and the picture changes under it.
 *
 * **The canvas gets less room than it does in the editor, deliberately.** Composing a team
 * is a job for the whole screen; reading a run is a job for the statuses on the boxes and
 * what the agents wrote, and the outputs have a window of their own
 * (`RunOutputsDialog`). The list above is worth its share of the height because picking the
 * next run is half of what this view is for.
 */
export function TeamRunsView({
  api,
  teamId,
  teamName,
  models,
  initialRunId,
  onClose,
  onEdit,
}: {
  api: TeamsApi;
  teamId: number;
  teamName: string;
  models: TeamsModel[];
  /** A run to open on arrival — the one just started from the catalogue. `null` waits for
   *  the operator to pick, which is the ordinary case of coming here to look around. */
  initialRunId: number | null;
  onClose(): void;
  /** Back into the editor for this team — the other direction of the same short loop the
   *  editor's own `Runs →` opens (`TeamRunsStrip`). */
  onEdit(): void;
}) {
  const [runs, setRuns] = useState<TeamRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState<number | null>(initialRunId);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    api
      .listRuns(teamId, controller.signal)
      .then((answer) => {
        if (cancelled) return;
        setRuns(answer);
        // Newest first is the module's order, and the newest run is what somebody arriving
        // here almost always means. Only when nothing is being watched yet: a reload must
        // not move the operator off the run they were reading.
        setWatching((current) => current ?? answer[0]?.id ?? null);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "the runs could not be read");
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, teamId, attempt]);

  // `run_team` is a chat tool, so a run can appear while this view is open and nothing
  // about it passes through here (`agentActivity.ts`).
  useAgentTurns(() => setAttempt((n) => n + 1));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
        >
          ← Catalogue
        </button>
        <span className="text-sm text-ink">
          {teamName} <span className="text-xs text-ink-faint">· runs</span>
        </span>
        <button
          type="button"
          onClick={onEdit}
          className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
        >
          ← Edit team
        </button>
        {runs !== null && (
          <span className="text-xs text-ink-faint">
            {runs.length} recorded{runs.length > 0 && ", newest first"}
          </span>
        )}
      </header>

      <div className="max-h-[30vh] shrink-0 overflow-auto border-b border-border">
        {error && (
          <p className="px-2 py-1 text-xs text-critical">
            {error}
            <button
              type="button"
              onClick={() => setAttempt((n) => n + 1)}
              className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
            >
              Retry
            </button>
          </p>
        )}
        {runs === null && !error && <p className="px-2 py-2 text-xs text-ink-muted">Reading the runs…</p>}
        {runs !== null && runs.length === 0 && (
          <p className="px-2 py-2 text-xs text-ink-muted">
            No runs yet. Start one from the catalogue, or let a schedule do it.
          </p>
        )}
        {runs !== null && runs.length > 0 && (
          <ul className="flex flex-col">
            {runs.map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  onClick={() => setWatching(run.id)}
                  aria-pressed={watching === run.id}
                  className={`flex w-full items-baseline justify-between gap-3 px-2 py-1 text-left text-xs ${
                    watching === run.id
                      ? "bg-primary-soft text-ink"
                      : "text-ink-muted hover:bg-panel-strong hover:text-ink"
                  }`}
                >
                  <span>
                    Run {run.id}
                    <span className={`ml-2 ${RUN_TONE[run.status] ?? "text-ink-faint"}`}>
                      {run.status}
                    </span>
                  </span>
                  <span className="text-ink-faint">
                    {run.startedAt !== null ? formatInstant(run.startedAt) : "not started"}
                    {run.finishedAt !== null && ` → ${formatInstant(run.finishedAt)}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="min-h-0 flex-1">
        {watching === null ? (
          <p className="p-4 text-sm text-ink-muted">Pick a run to see it on the team's picture.</p>
        ) : (
          // Keyed by the run, so switching runs rebuilds the monitor rather than handing a
          // new id to a component still holding the previous run's stream and steps.
          <RunMonitor key={watching} api={api} runId={watching} models={models} />
        )}
      </div>
    </div>
  );
}

/** The same vocabulary and the same colours the badge on a run uses — one status word, read
 *  the same way in the list and on the run itself. */
const RUN_TONE: Record<string, string> = {
  pending: "text-ink-muted",
  running: "text-primary",
  completed: "text-good",
  failed: "text-critical",
  cancelled: "text-warning",
};
