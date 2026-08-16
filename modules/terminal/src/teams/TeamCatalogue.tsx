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
 * Starting a run is not here yet: the module has no route for one until the run groups
 * land, and a button that cannot do anything is worse than one that is not there.
 */
export function TeamCatalogue({
  teams,
  status,
  error,
  api,
  onOpen,
  onNew,
  onChanged,
  onReload,
}: {
  teams: TeamSummary[];
  status: "loading" | "ready" | "error";
  error: string | null;
  api: TeamsApi;
  onOpen(id: number): void;
  onNew(): void;
  onChanged(): void;
  onReload(): void;
}) {
  const [retiring, setRetiring] = useState<TeamSummary | null>(null);

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

      <ul className="flex flex-col gap-2">
        {teams.map((team) => (
          <li
            key={team.id}
            className="flex items-center justify-between gap-3 rounded border border-border bg-panel px-3 py-2"
          >
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
