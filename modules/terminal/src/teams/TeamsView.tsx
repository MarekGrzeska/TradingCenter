import { useState } from "react";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { useAgentTurns } from "../agent/useAgentTurns";
import { MemoryPanel } from "./MemoryPanel";
import { SchedulesPanel } from "./SchedulesPanel";
import { TeamCatalogue } from "./TeamCatalogue";
import { TeamEditor } from "./TeamEditor";
import { TeamRunsView } from "./TeamRunsView";
import { teamsApi, type TeamsApi } from "./teamsApi";
import { useModels, useTeams, useTools } from "./useTeamsData";

type Open =
  | { kind: "catalogue" }
  | { kind: "team"; id: number }
  | { kind: "new" }
  /** A team's runs, with one of them open underneath the list. `runId` is set when the
   *  operator arrived by starting a run or by following one from a schedule's history;
   *  `null` lets the view open the newest, which is what "show me the runs" means. */
  | { kind: "runs"; teamId: number; teamName: string; runId: number | null }
  | { kind: "schedules"; teamId: number; teamName: string }
  | { kind: "memory"; teamId: number; teamName: string };

/**
 * The catalogue, one team open on the canvas, one run watched on it. The model catalogue is read here because
 * both children need it and a team cannot be opened without it — this terminal has no model id of its own.
 */
export function TeamsView({ api = teamsApi }: { api?: TeamsApi } = {}) {
  const teams = useTeams(api);
  const models = useModels(api);
  const tools = useTools(api);
  const [open, setOpen] = useState<Open>({ kind: "catalogue" });

  // A chat can create and revise teams, and that write never passes through this tab, so a team the model made
  // existed everywhere but on screen. Only the catalogue: a team open on the canvas is a draft being typed into.
  useAgentTurns(teams.reload);

  if (models.status === "loading") {
    return <p className="p-4 text-sm text-ink-muted">Reading the model catalogue…</p>;
  }
  if (models.status === "error") {
    // Without it nothing here can be edited, so this is the whole tab's failure rather
    // than a corner of it.
    return (
      <UnreachableNotice className="p-4 text-sm text-critical" onRetry={models.reload}>
        {models.error}
      </UnreachableNotice>
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
        onWatch={(runId, teamId, teamName) =>
          setOpen({ kind: "runs", teamId, teamName, runId })
        }
        onRuns={(teamId, teamName) => setOpen({ kind: "runs", teamId, teamName, runId: null })}
        onNew={() => setOpen({ kind: "new" })}
        onSchedules={(id, name) => setOpen({ kind: "schedules", teamId: id, teamName: name })}
        onMemory={(id, name) => setOpen({ kind: "memory", teamId: id, teamName: name })}
        onChanged={teams.reload}
        onReload={teams.reload}
      />
    );
  }

  if (open.kind === "runs") {
    // Leaving this view stops nothing: the monitor drops its stream, the run carries on,
    // and this list is the way back to it.
    return (
      <TeamRunsView
        api={api}
        teamId={open.teamId}
        teamName={open.teamName}
        models={models.value}
        initialRunId={open.runId}
        onClose={() => setOpen({ kind: "catalogue" })}
        onEdit={() => setOpen({ kind: "team", id: open.teamId })}
      />
    );
  }

  if (open.kind === "schedules") {
    return (
      <SchedulesPanel
        api={api}
        teamId={open.teamId}
        teamName={open.teamName}
        tools={tools.value}
        onClose={() => setOpen({ kind: "catalogue" })}
        onWatchRun={(runId) =>
          setOpen({ kind: "runs", teamId: open.teamId, teamName: open.teamName, runId })
        }
      />
    );
  }

  if (open.kind === "memory") {
    return (
      <MemoryPanel
        api={api}
        teamId={open.teamId}
        teamName={open.teamName}
        onClose={() => setOpen({ kind: "catalogue" })}
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
      onRuns={(runId, teamName) => {
        if (open.kind !== "team") return;
        setOpen({ kind: "runs", teamId: open.id, teamName, runId });
      }}
    />
  );
}
