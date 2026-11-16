import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import type { TeamsApi, TeamSummary } from "./teamsApi";

const NO_TEAMS: TeamSummary[] = [];

/**
 * The other side of `Retire`: what was taken out of the catalogue, and the way back. Restoring brings the team back
 * and nothing else — its schedules stay off, so a team on the live account does not resume trading on a click.
 */
export function RetiredTeams({
  api,
  onClose,
  onRestored,
}: {
  api: TeamsApi;
  onClose(): void;
  /** The catalogue has one more team now; the view behind reads it again. */
  onRestored(): void;
}) {
  const retired = useRead<TeamSummary[]>({
    key: ["teams", "retired"],
    read: (signal) => api.listRetiredTeams(signal),
    initial: NO_TEAMS,
    fallbackMessage: "could not read the retired teams",
  });
  const [restoring, setRestoring] = useState<TeamSummary | null>(null);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center gap-2">
        <Button onClick={onClose}>← Teams</Button>
        <h2 className="text-sm font-semibold text-ink">Retired teams</h2>
      </div>

      {retired.status === "loading" && (
        <p className="text-sm text-ink-muted">Reading the retired teams…</p>
      )}
      {retired.status === "error" && (
        <UnreachableNotice onRetry={retired.reload}>{retired.error}</UnreachableNotice>
      )}
      {retired.status === "ready" && retired.value.length === 0 && (
        <p className="text-sm text-ink-muted">No retired teams.</p>
      )}

      <ul className="flex flex-col gap-2">
        {retired.value.map((team) => (
          <li
            key={team.id}
            className="flex items-center justify-between gap-3 rounded border border-border bg-panel px-3 py-2"
          >
            <div className="min-w-0">
              <div className="truncate text-sm text-ink">{team.name}</div>
              <div className="truncate text-xs text-ink-muted">{team.description}</div>
              <div className="text-xs text-ink-faint">
                revision {team.latestRevision}
                {team.archivedAt != null && <> · retired {formatInstant(team.archivedAt)}</>}
              </div>
            </div>
            <Button tone="primary" onClick={() => setRestoring(team)}>
              Restore
            </Button>
          </li>
        ))}
      </ul>

      {restoring && (
        <ConfirmDialog
          title={`Restore ${restoring.name}?`}
          confirmLabel="Restore"
          busyLabel="Restoring…"
          fallbackError="the team could not be restored"
          onConfirm={async () => {
            await api.restoreTeam(restoring.id, new AbortController().signal);
            retired.reload();
            onRestored();
          }}
          onClose={() => setRestoring(null)}
        >
          <p className="text-sm text-ink">
            It returns to the catalogue with its revisions and runs. Its schedules and triggers stay
            switched off — turn each one on again in Schedules.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
