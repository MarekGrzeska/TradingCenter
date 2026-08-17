import { useEffect, useState } from "react";
import { MarketDataError } from "../data/types";
import { AgentSettingsDialog } from "./AgentSettingsDialog";
import { TeamCanvas } from "./TeamCanvas";
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
 * One team, on the canvas, with the team's own limits in the panel beside it and each
 * agent's settings in a dialog over it.
 *
 * The agents used to share that 20rem panel, one at a time. They no longer do: an agent has
 * a prompt, a guidance note, a tool list and its dependencies, and a column that narrow
 * made all four small at once. The gear on each box opens them in a wide dialog instead,
 * which leaves the panel to the one thing that belongs to the team rather than to any agent
 * — its trading limits, which are now always where they were rather than behind a button.
 *
 * `saved` is only ever set from something the module answered with — never from what is
 * being typed — so a refused save leaves the last confirmed revision to compare against
 * and the Save button keeps saying there is something unsaved. `PromptManagementView`
 * holds the same rule for the same reason.
 *
 * Nothing here checks whether the draft is valid. The module decides that, and its
 * refusal is put next to the agent or the dependency it names (`refusal.ts`); a second
 * opinion in the browser would only be a second thing that can be wrong.
 */
export function TeamEditor({
  api,
  teamId,
  models,
  tools,
  toolsNote,
  onClose,
  onCreated,
}: {
  api: TeamsApi;
  /** `null` opens a team that does not exist yet — saving it is what creates it. */
  teamId: number | null;
  models: TeamsModel[];
  tools: TeamsTool[];
  toolsNote: string | null;
  onClose(): void;
  onCreated(team: TeamSummary): void;
}) {
  // The cheapest model in the catalogue is what a new agent starts on — the module
  // publishes the order, so the terminal picks a position in it rather than a name
  // (`terminal-teams`, "terminal nie ma w swoim kodzie ani jednego identyfikatora
  // modelu").
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
  // Where the operator left each agent. Kept beside the draft rather than in it: the
  // module stores it beside the revision for the same reason, and a moved node must not
  // make the Save button light up (specs/terminal-teams, "Przesunięcie nie jest zmianą
  // definicji").
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

  // Ctrl+Z on the document, so it reaches the draft wherever the operator's hands are —
  // except inside something being typed into, where the browser's own undo is the better
  // one and taking it away would be a worse trade than not having the shortcut at all.
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
    // The refusal described the definition that was sent, so the first edit after it
    // retires it — leaving it on would keep a node marked for a reason that may already
    // be gone, which is worse than saying nothing.
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
    // Fire and forget on purpose, and the failure is deliberately quiet: the node is
    // already where the operator put it, and an error banner over a position is louder
    // than what was lost.
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

  // Looked up in the draft rather than trusted from state: an agent removed by `Undo` while
  // its settings are open takes the dialog with it, instead of leaving one over fields that
  // edit an agent the definition no longer has.
  const settingsAgent = draft.agents.find((agent) => agent.key === settingsKey) ?? null;
  const dirty = saved === null || hasChanges(draft, saved);

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

        <button
          type="button"
          onClick={takeBack}
          disabled={history.length === 0}
          title="Undo the last change (Ctrl+Z)"
          className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong disabled:cursor-not-allowed disabled:opacity-40"
        >
          Undo
        </button>
        {/* No "Team" button any more: the right-hand column is the team's, always, so
            there is nothing to come back from. */}
        <button
          type="button"
          onClick={() => edit(addAgent(draft, defaultModelId))}
          className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
        >
          Add agent
        </button>
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty}
          className="cursor-pointer rounded border border-primary-line bg-primary-soft px-3 py-1 text-xs text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? "Saving…" : teamId === null ? "Create team" : "Save revision"}
        </button>
        {dirty && !saving && <span className="text-xs text-ink-faint">unsaved changes</span>}
      </header>

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
