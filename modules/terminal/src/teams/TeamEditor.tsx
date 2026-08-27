import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { MarketDataError } from "../data/types";
import { AgentSettingsDialog } from "./AgentSettingsDialog";
import { TeamCanvas } from "./TeamCanvas";
import { TeamRunsStrip } from "./TeamRunsStrip";
import { TeamPanel } from "./TeamPanel";
import { NO_HISTORY, kindForPatch, remember, undo, type EditHistory } from "./editHistory";
import { locateRefusal, type Refusal } from "./refusal";
import {
  addAgent,
  addDependency,
  emptyDefinition,
  hasChanges,
  removeAgent,
  removeDependency,
  setTradingLimit,
  updateAgent,
} from "./teamDraft";
import type {
  TeamDefinition,
  TeamDependency,
  TeamLayout,
  TeamSummary,
  TeamsApi,
  TeamsModel,
  TeamsTool,
} from "./teamsApi";

/**
 * One team on the canvas: the team's limits in the panel, each agent's settings in a dialog, because a 20rem
 * column made a prompt, a note, a tool list and dependencies all small at once. Validity is the module's call.
 */
export function TeamEditor({
  api,
  teamId,
  models,
  tools,
  toolsNote,
  onClose,
  onCreated,
  onRuns,
}: {
  api: TeamsApi;
  /** `null` opens a team that does not exist yet — saving it is what creates it. */
  teamId: number | null;
  models: TeamsModel[];
  tools: TeamsTool[];
  toolsNote: string | null;
  onClose(): void;
  onCreated(team: TeamSummary): void;
  /** Leaves editing for the runs of this team — a run id to open that one, `null` for the
   *  list. The name travels with it: this editor read it from the module and the runs view
   *  puts it in its own header, so nothing has to look it up a second time. Never called
   *  for a team that does not exist yet — it has no runs to look at. */
  onRuns(runId: number | null, teamName: string): void;
}) {
  // The cheapest model in the catalogue is what a new agent starts on — the module publishes the order, so
  // the terminal picks a position rather than a name (`terminal-teams`, no model identifier in this code).
  const defaultModelId = [...models].sort((a, b) => a.costRank - b.costRank)[0]?.id ?? "";

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [saved, setSaved] = useState<TeamDefinition | null>(null);
  const [draft, setDraft] = useState<TeamDefinition | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // Which agent's settings are open, which is not the same as which one is selected: the
  // canvas marks a selection, and closing the dialog leaves that mark where it was.
  const [settingsKey, setSettingsKey] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Where the operator left each agent, beside the draft rather than in it: a moved node must not light up
  // the Save button (specs/terminal-teams, "Przesunięcie nie jest zmianą definicji").
  const [places, setPlaces] = useState<TeamLayout>(new Map());
  // What one step back restores, deepest last. Emptied when another team is opened: this
  // is the history of what the operator did to *this* draft.
  const [history, setHistory] = useState<EditHistory>(NO_HISTORY);

  useEffect(() => {
    if (teamId === null) {
      const fresh = emptyDefinition(defaultModelId);
      setSaved(null);
      setDraft(fresh);
      setVersion(null);
      setPlaces(new Map());
      setHistory(NO_HISTORY);
      setSelectedKey(fresh.agents[0]?.key ?? null);
      setSettingsKey(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setError(null);

    Promise.all([
      api.getTeam(teamId, controller.signal),
      api.latestRevision(teamId, controller.signal),
      // Its own read, and its failure is not the team's: a layout that cannot be fetched
      // leaves every agent placed by `layout()`, which is where they all started anyway.
      api.layout(teamId, controller.signal).catch(() => new Map()),
    ])
      .then(([team, revision, layout]) => {
        if (cancelled) return;
        setName(team.name);
        setDescription(team.description);
        setVersion(revision.version);
        setSaved(revision.definition);
        setDraft(revision.definition);
        setPlaces(layout);
        setHistory(NO_HISTORY);
        setSelectedKey(revision.definition.agents[0]?.key ?? null);
        setSettingsKey(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "could not open the team");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, teamId]);

  // Ctrl+Z on the document, so it reaches the draft wherever the hands are — except inside a field, where
  // the browser's own undo is better and taking it away would be the worse trade.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "z" || !(event.ctrlKey || event.metaKey)) return;
      if (event.shiftKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable || ["INPUT", "TEXTAREA"].includes(target.tagName))
      ) {
        return;
      }
      event.preventDefault();
      takeBack();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  });

  function edit(next: TeamDefinition, kind = "structure") {
    if (draft) setHistory((current) => remember(current, { definition: draft, places }, kind));
    setDraft(next);
    // The refusal described the definition that was sent, so the first edit after it retires it: a node
    // marked for a reason that may already be gone is worse than saying nothing.
    setRefusal(null);
  }

  function move(agentKey: string, at: { x: number; y: number }) {
    if (draft) {
      setHistory((current) =>
        remember(current, { definition: draft, places }, `move:${agentKey}`),
      );
    }
    place(new Map(places).set(agentKey, at));
  }

  function place(moved: TeamLayout) {
    setPlaces(moved);
    // A team that does not exist yet has nowhere to put this; it is saved with the rest
    // of the arrangement the first time the operator drags something after creating it.
    if (teamId === null) return;
    // Fire and forget, and the failure is deliberately quiet: the node is already where the operator put
    // it, and an error banner over a position is louder than what was lost.
    void api.saveLayout(teamId, moved, new AbortController().signal).catch(() => {});
  }

  function takeBack() {
    const step = undo(history);
    if (step === null) return;
    setHistory(step.history);
    setDraft(step.state.definition);
    setRefusal(null);
    // The arrangement travels with the rest of the step and is written back the same way a
    // drag writes it: a node put back where it was is only put back if the module agrees.
    if (step.state.places !== places) place(step.state.places);
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    const signal = new AbortController().signal;
    try {
      if (teamId === null) {
        const team = await api.createTeam(name, description, draft, signal);
        setRefusal(null);
        onCreated(team);
        return;
      }
      const revision = await api.saveRevision(teamId, draft, signal);
      setSaved(revision.definition);
      setDraft(revision.definition);
      setVersion(revision.version);
      setRefusal(null);
    } catch (cause) {
      if (cause instanceof MarketDataError && cause.kind === "refused") {
        const located = locateRefusal(cause.message, draft);
        setRefusal(located);
        // Open the settings of the agent the module named, so the reason is next to the
        // fields it is about rather than in a corner of the screen.
        if (located.agents.length > 0) {
          setSelectedKey(located.agents[0]);
          setSettingsKey(located.agents[0]);
        } else setError(cause.message);
      } else {
        setError(cause instanceof Error ? cause.message : "could not save the team");
      }
    } finally {
      setSaving(false);
    }
  }

  if (!draft) {
    return (
      <div className="p-4 text-sm text-ink-muted">
        {error ? <span className="text-critical">{error}</span> : "Opening the team…"}
      </div>
    );
  }

  // Looked up in the draft rather than trusted from state: an agent removed by `Undo` takes its open
  // dialog with it, instead of leaving fields that edit an agent the definition no longer has.
  const settingsAgent = draft.agents.find((agent) => agent.key === settingsKey) ?? null;
  const dirty = saved === null || hasChanges(draft, saved);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <Button onClick={onClose}>
          ← Catalogue
        </Button>
        {teamId === null ? (
          <>
            <input
              aria-label="Team name"
              placeholder="Team name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
            />
            <input
              aria-label="Team description"
              placeholder="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-w-48 flex-1 rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
            />
          </>
        ) : (
          <span className="text-sm text-ink">
            {name} <span className="text-xs text-ink-faint">revision {version}</span>
          </span>
        )}

        {/* The other half of the loop this view is one half of: change something, run it,
            read what came out. It used to go through the catalogue every time it turned. */}
        {teamId !== null && (
          <Button onClick={() => onRuns(null, name)}>
            Runs →
          </Button>
        )}
        <Button
          onClick={takeBack}
          disabled={history.length === 0}
          title="Undo the last change (Ctrl+Z)"
        >
          Undo
        </Button>
        {/* No "Team" button any more: the right-hand column is the team's, always, so
            there is nothing to come back from. */}
        <Button onClick={() => edit(addAgent(draft, defaultModelId))}>
          Add agent
        </Button>
        <Button
          tone="primary"
          size="md"
          onClick={save}
          disabled={saving || !dirty}
        >
          {saving ? "Saving…" : teamId === null ? "Create team" : "Save revision"}
        </Button>
        {dirty && !saving && <span className="text-xs text-ink-faint">unsaved changes</span>}
      </header>

      {teamId !== null && (
        <TeamRunsStrip api={api} teamId={teamId} onOpen={(runId) => onRuns(runId, name)} />
      )}

      {error && <p className="border-b border-border px-2 py-1 text-xs text-critical">{error}</p>}
      {/* Also shown here, and not only on the node: a refusal naming an agent the canvas
          has scrolled away from is a refusal nobody reads. */}
      {refusal && (
        <p className="border-b border-border px-2 py-1 text-xs text-critical">{refusal.message}</p>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_20rem]">
        <TeamCanvas
          definition={draft}
          models={models}
          selectedKey={selectedKey}
          refusal={refusal}
          places={places}
          onSelect={setSelectedKey}
          onOpenSettings={setSettingsKey}
          onMove={move}
          onConnect={(edge: TeamDependency) => edit(addDependency(draft, edge))}
          onDisconnect={(edge: TeamDependency) => edit(removeDependency(draft, edge))}
        />
        <TeamPanel
          trading={draft.trading}
          onChange={(patch, kind) => edit(setTradingLimit(draft, patch), kind)}
        />
      </div>

      {settingsAgent && (
        <AgentSettingsDialog
          agent={settingsAgent}
          definition={draft}
          models={models}
          tools={tools}
          toolsNote={toolsNote}
          refusal={refusal}
          onChange={(patch) =>
            edit(
              updateAgent(draft, settingsAgent.key, patch),
              kindForPatch(settingsAgent.key, patch),
            )
          }
          onClose={() => setSettingsKey(null)}
          onRemove={() => {
            edit(removeAgent(draft, settingsAgent.key));
            setSettingsKey(null);
            if (selectedKey === settingsAgent.key) setSelectedKey(null);
          }}
          onConnect={(edge) => edit(addDependency(draft, edge))}
          onDisconnect={(edge) => edit(removeDependency(draft, edge))}
        />
      )}
    </div>
  );
}
