import { useState } from "react";
import { TeamCatalogue } from "./TeamCatalogue";
import { TeamEditor } from "./TeamEditor";
import { teamsApi, type TeamsApi } from "./teamsApi";
import { useModels, useTeams, useTools } from "./useTeamsData";

type Open = { kind: "catalogue" } | { kind: "team"; id: number } | { kind: "new" };

/**
 * The teams tab: the catalogue, and one team open on the canvas.
 *
 * The model catalogue is read here rather than inside the editor because both children
 * need it — the canvas to label a node with a model's name, the panel to offer the
 * picker — and because a team cannot be opened without it: a new agent needs a model id,
 * and this terminal has none of its own to fall back on (`terminal-teams`).
 */
export function TeamsView({ api = teamsApi }: { api?: TeamsApi } = {}) {
  const teams = useTeams(api);
  const models = useModels(api);
  const tools = useTools(api);
  const [open, setOpen] = useState<Open>({ kind: "catalogue" });

  if (models.status === "loading") {
    return <p className="p-4 text-sm text-ink-muted">Reading the model catalogue…</p>;
  }
  if (models.status === "error") {
    // Without it nothing here can be edited, so this is the whole tab's failure rather
    // than a corner of it.
    return (
      <p className="p-4 text-sm text-critical">
        {models.error}
        <button
          type="button"
          onClick={models.reload}
          className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </p>
    );
  }

  if (open.kind === "catalogue") {
    return (
      <TeamCatalogue
        teams={teams.value}
        status={teams.status}
        error={teams.error}
        api={api}
        onOpen={(id) => setOpen({ kind: "team", id })}
        onNew={() => setOpen({ kind: "new" })}
        onChanged={teams.reload}
        onReload={teams.reload}
      />
    );
  }

  return (
    <TeamEditor
      api={api}
      teamId={open.kind === "team" ? open.id : null}
      models={models.value}
      tools={tools.value}
      toolsNote={
        tools.status === "error"
          ? `the tool list could not be read — ${tools.error}`
          : "the module announces no tools"
      }
      onClose={() => {
        teams.reload();
        setOpen({ kind: "catalogue" });
      }}
      onCreated={(team) => {
        teams.reload();
        setOpen({ kind: "team", id: team.id });
      }}
    />
  );
}
