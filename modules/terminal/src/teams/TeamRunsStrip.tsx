import { useAgentTurns } from "../agent/useAgentTurns";
import { useRead } from "../data/query";
import { formatInstant } from "../ui/formatTime";
import { NO_RUNS, runsKey } from "./runsRead";
import type { TeamsApi } from "./teamsApi";

/** How many fit on one line before the strip starts hiding things. Six because that is
 *  about a day of a schedule firing every few hours, and the rest is a click away. */
const SHOWN = 6;

/**
 * The team's last few runs on one line, because editing and reading a run are one loop that used to turn
 * through the catalogue. A strip, not a panel: enough to recognise a run — number, ending, time — and a way in.
 */
export function TeamRunsStrip({
  api,
  teamId,
  onOpen,
}: {
  api: TeamsApi;
  teamId: number;
  /** A run to open, or `null` for the whole list. */
  onOpen(runId: number | null): void;
}) {
  // The same cache entry `TeamRunsView` reads, so opening the runs from here draws the
  // list that is already in hand and asks the module once for both.
  const runs = useRead({
    key: runsKey(teamId),
    read: (signal) => api.listRuns(teamId, signal),
    initial: NO_RUNS,
    fallbackMessage: "the runs could not be read",
  });

  // A run started from the chat belongs on this line the moment it exists
  // (`agentActivity.ts`).
  useAgentTurns(runs.reload);

  // A strip that cannot be read says nothing rather than taking a corner of the editor for
  // an error about something nobody asked for yet. The run view says it properly.
  if (runs.status !== "ready" || runs.value.length === 0) return null;

  return (
    <div className="flex items-center gap-2 overflow-x-auto border-b border-border px-2 py-1">
      <span className="shrink-0 text-xs uppercase tracking-wide text-ink-faint">Runs</span>
      {runs.value.slice(0, SHOWN).map((run) => (
        <button
          key={run.id}
          type="button"
          onClick={() => onOpen(run.id)}
          title={
            run.startedAt !== null
              ? `Run ${run.id} · ${run.status} · started ${formatInstant(run.startedAt)}`
              : `Run ${run.id} · ${run.status}`
          }
          className="shrink-0 cursor-pointer rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:border-primary-line hover:bg-panel-strong hover:text-ink"
        >
          {run.id}
          <span className={`ml-1.5 ${RUN_TONE[run.status] ?? "text-ink-faint"}`}>
            {run.status}
          </span>
        </button>
      ))}
      <button
        type="button"
        onClick={() => onOpen(null)}
        className="shrink-0 cursor-pointer rounded border border-transparent px-2 py-0.5 text-xs text-ink-muted underline underline-offset-2 hover:text-ink"
      >
        {runs.value.length > SHOWN ? `all ${runs.value.length} runs →` : "open runs →"}
      </button>
    </div>
  );
}

/** The same words in the same colours as the badge on a run and the rows in `TeamRunsView`. */
const RUN_TONE: Record<string, string> = {
  pending: "text-ink-muted",
  running: "text-primary",
  completed: "text-good",
  failed: "text-critical",
  cancelled: "text-warning",
};
