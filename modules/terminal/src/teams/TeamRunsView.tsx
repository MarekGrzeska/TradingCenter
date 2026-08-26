import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { useAgentTurns } from "../agent/useAgentTurns";
import { useRead } from "../data/query";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import { RunMonitor } from "./RunMonitor";
import type { TeamRun } from "./runs";
import { NO_RUNS, runsKey } from "./runsRead";
import type { TeamRevision, TeamsApi, TeamsModel } from "./teamsApi";

/**
 * One team's runs, the picked one drawn underneath — replacing a drawer that cost two clicks and then moved the
 * operator elsewhere. The canvas gets less room than in the editor: reading a run is not composing one.
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
  const [watching, setWatching] = useState<number | null>(initialRunId);
  const [starting, setStarting] = useState(false);

  const runList = useRead({
    key: runsKey(teamId),
    read: (signal) => api.listRuns(teamId, signal),
    initial: NO_RUNS,
    fallbackMessage: "the runs could not be read",
  });
  const runs = runList.status === "loading" ? null : runList.value;
  const error = runList.error;

  // Newest first is the module's order, and the newest run is what somebody arriving here almost always
  // means. Only when nothing is being watched yet: a reload must not move the operator off their run.
  useEffect(() => {
    setWatching((current) => current ?? runList.value[0]?.id ?? null);
  }, [runList.value]);

  // `run_team` is a chat tool, so a run can appear while this view is open and nothing
  // about it passes through here (`agentActivity.ts`).
  useAgentTurns(runList.reload);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <Button onClick={onClose}>
          ← Catalogue
        </Button>
        <span className="text-sm text-ink">
          {teamName} <span className="text-xs text-ink-faint">· runs</span>
        </span>
        <Button onClick={onEdit}>
          ← Edit team
        </Button>
        <Button
          tone="primary"
          onClick={() => setStarting(true)}
        >
          ▶ Run now
        </Button>
        {runs !== null && (
          <span className="text-xs text-ink-faint">
            {runs.length} recorded{runs.length > 0 && ", newest first"}
          </span>
        )}
      </header>

      {starting && (
        <StartRunDialog
          api={api}
          teamId={teamId}
          teamName={teamName}
          onClose={() => setStarting(false)}
          onStarted={(run) => {
            setWatching(run.id);
            runList.reload();
          }}
        />
      )}

      <div className="max-h-[30vh] shrink-0 overflow-auto border-b border-border">
        {error && (
          <UnreachableNotice className="px-2 py-1 text-xs text-critical" onRetry={runList.reload}>
            {error}
          </UnreachableNotice>
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

/**
 * A dialog rather than a button that just fires, because a run costs tokens and, with the order tools, places
 * demo orders. Which revision runs is not a choice — the module runs the latest, so it is read and shown.
 */
function StartRunDialog({
  api,
  teamId,
  teamName,
  onClose,
  onStarted,
}: {
  api: TeamsApi;
  teamId: number;
  teamName: string;
  onClose(): void;
  onStarted(run: TeamRun): void;
}) {
  const [revision, setRevision] = useState<TeamRevision | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    api
      .latestRevision(teamId, controller.signal)
      .then((answer) => !cancelled && setRevision(answer))
      .catch(() => undefined);
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, teamId]);

  return (
    <ConfirmDialog
      title="Run now"
      confirmLabel="Start the run"
      busyLabel="Starting…"
      fallbackError="the run could not be started"
      onConfirm={async () => {
        onStarted(await api.startRun(teamId, new AbortController().signal));
      }}
      onClose={onClose}
    >
      <p>
        Start <span className="text-ink">{teamName}</span> on{" "}
        {revision === null ? (
          "its latest revision"
        ) : (
          <>
            revision <span className="text-ink">{revision.version}</span> — the team's latest
          </>
        )}
        . It runs the same way a schedule would: the same limits, the same trace.
      </p>
    </ConfirmDialog>
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
