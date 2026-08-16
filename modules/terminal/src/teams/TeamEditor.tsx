import { useEffect, useState } from "react";
import { MarketDataError } from "../data/types";
import { AgentPanel } from "./AgentPanel";
import { TeamCanvas } from "./TeamCanvas";
import { TeamLimitsPanel } from "./TeamLimitsPanel";
import { locateRefusal, type Refusal } from "./refusal";
import {
  addAgent,
  addDependency,
  emptyDefinition,
  hasChanges,
  removeAgent,
  removeDependency,
  setTradingLimits,
  updateAgent,
} from "./teamDraft";
import type {
  TeamDefinition,
  TeamDependency,
  TeamSummary,
  TeamsApi,
  TeamsModel,
  TeamsTool,
} from "./teamsApi";

/**
 * One team, on the canvas and in the panel beside it.
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
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (teamId === null) {
      const fresh = emptyDefinition(defaultModelId);
      setSaved(null);
      setDraft(fresh);
      setVersion(null);
      setSelectedKey(fresh.agents[0]?.key ?? null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setError(null);

    Promise.all([api.getTeam(teamId, controller.signal), api.latestRevision(teamId, controller.signal)])
      .then(([team, revision]) => {
        if (cancelled) return;
        setName(team.name);
        setDescription(team.description);
        setVersion(revision.version);
        setSaved(revision.definition);
        setDraft(revision.definition);
        setSelectedKey(revision.definition.agents[0]?.key ?? null);
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

  function edit(next: TeamDefinition) {
    setDraft(next);
    // The refusal described the definition that was sent, so the first edit after it
    // retires it — leaving it on would keep a node marked for a reason that may already
    // be gone, which is worse than saying nothing.
    setRefusal(null);
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
        // Open the panel on the agent the module named, so the reason is next to the
        // thing it is about rather than in a corner of the screen.
        if (located.agents.length > 0) setSelectedKey(located.agents[0]);
        else setError(cause.message);
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

  const selected = draft.agents.find((agent) => agent.key === selectedKey) ?? null;
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
          onSelect={setSelectedKey}
          onConnect={(edge: TeamDependency) => edit(addDependency(draft, edge))}
          onDisconnect={(edge: TeamDependency) => edit(removeDependency(draft, edge))}
        />
        {selected ? (
          <AgentPanel
            agent={selected}
            definition={draft}
            models={models}
            tools={tools}
            toolsNote={toolsNote}
            refusal={refusal}
            onChange={(patch) => edit(updateAgent(draft, selected.key, patch))}
            onRemove={() => {
              edit(removeAgent(draft, selected.key));
              setSelectedKey(null);
            }}
            onDisconnect={(edge) => edit(removeDependency(draft, edge))}
          />
        ) : (
          // Nothing selected is the team itself — where its own settings live, rather
          // than behind a dialog the operator has to know exists.
          <TeamLimitsPanel
            trading={draft.trading}
            onChange={(patch) => edit(setTradingLimits(draft, patch))}
          />
        )}
      </div>
    </div>
  );
}
