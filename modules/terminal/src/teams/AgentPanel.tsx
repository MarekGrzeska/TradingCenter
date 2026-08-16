import type { Refusal } from "./refusal";
import type { TeamAgent, TeamDefinition, TeamDependency, TeamsModel, TeamsTool } from "./teamsApi";

/**
 * One agent, edited where it is looked at (`terminal-teams`, "Operator składa zespół w
 * tym samym widoku, w którym go ogląda").
 *
 * Both pickers are built from what the module publishes — `models` from its catalogue,
 * `tools` from what its tool server announces — and this file names no model and no tool
 * of its own. That is the requirement, not an implementation detail: adding a model is a
 * line in the module's configuration, and a terminal carrying its own list would make it
 * a release here too.
 */
export function AgentPanel({
  agent,
  definition,
  models,
  tools,
  toolsNote,
  refusal,
  onChange,
  onRemove,
  onDisconnect,
}: {
  agent: TeamAgent;
  definition: TeamDefinition;
  models: TeamsModel[];
  tools: TeamsTool[];
  /** Why the tool list is empty, when it is — an unreachable or unconfigured tool server
   *  is a working state, and the panel says which rather than showing an empty box. */
  toolsNote: string | null;
  refusal: Refusal | null;
  onChange(patch: Partial<Omit<TeamAgent, "key">>): void;
  onRemove(): void;
  onDisconnect(edge: TeamDependency): void;
}) {
  const incoming = definition.dependencies.filter((edge) => edge.to === agent.key);
  const outgoing = definition.dependencies.filter((edge) => edge.from === agent.key);
  const roleOf = (key: string) =>
    definition.agents.find((candidate) => candidate.key === key)?.role ?? key;
  const refusedHere = refusal?.agents.includes(agent.key) ?? false;
  // A model that was in the catalogue when the revision was saved and is not now still
  // has to appear in the picker — otherwise selecting nothing silently rewrites the
  // agent onto whatever sits first in the list.
  const modelMissing = !models.some((model) => model.id === agent.modelId);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto border-l border-border p-3">
      {refusedHere && refusal && (
        <p className="rounded border border-critical bg-panel px-2 py-1 text-xs text-critical">
          {refusal.message}
        </p>
      )}

      <Field id="agent-role" label="Role">
        <input
          id="agent-role"
          value={agent.role}
          onChange={(event) => onChange({ role: event.target.value })}
          className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
        />
      </Field>

      <Field id="agent-model" label="Model">
        <select
          id="agent-model"
          value={agent.modelId}
          onChange={(event) => onChange({ modelId: event.target.value })}
          className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
        >
          {modelMissing && <option value={agent.modelId}>{agent.modelId} (withdrawn)</option>}
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.displayName}
            </option>
          ))}
        </select>
      </Field>

      <Field id="agent-prompt" label="Prompt">
        <textarea
          id="agent-prompt"
          rows={5}
          value={agent.prompt}
          onChange={(event) => onChange({ prompt: event.target.value })}
          className="w-full rounded border border-border bg-panel px-2 py-1 font-mono text-xs text-ink"
        />
      </Field>

      <Field id="agent-guidance" label="Guidance">
        <textarea
          id="agent-guidance"
          rows={3}
          value={agent.guidance}
          onChange={(event) => onChange({ guidance: event.target.value })}
          className="w-full rounded border border-border bg-panel px-2 py-1 font-mono text-xs text-ink"
        />
      </Field>

      <fieldset className="flex flex-col gap-1">
        <legend className="text-xs uppercase tracking-wide text-ink-faint">Tools</legend>
        {tools.length === 0 ? (
          <p className="text-xs text-ink-muted">{toolsNote ?? "the module announces no tools"}</p>
        ) : (
          tools.map((tool) => (
            <label key={tool.name} className="flex items-start gap-2 text-xs text-ink">
              <input
                type="checkbox"
                checked={agent.tools.includes(tool.name)}
                onChange={(event) =>
                  onChange({
                    tools: event.target.checked
                      ? [...agent.tools, tool.name]
                      : agent.tools.filter((name) => name !== tool.name),
                  })
                }
              />
              <span>
                <span className="font-medium">{tool.name}</span>
                {tool.description && (
                  <span className="block text-ink-faint">{tool.description}</span>
                )}
              </span>
            </label>
          ))
        )}
        {/* Assigned by a revision saved earlier, and no longer announced. Left visible and
            removable rather than dropped quietly: this is what will refuse the next run
            (specs/teams-tool-access, "Narzędzie znika po stronie serwera"). */}
        {agent.tools
          .filter((name) => !tools.some((tool) => tool.name === name))
          .map((name) => (
            <label key={name} className="flex items-center gap-2 text-xs text-critical">
              <input
                type="checkbox"
                checked
                onChange={() => onChange({ tools: agent.tools.filter((tool) => tool !== name) })}
              />
              <span>{name} (not announced)</span>
            </label>
          ))}
      </fieldset>

      <section className="flex flex-col gap-1">
        <h4 className="text-xs uppercase tracking-wide text-ink-faint">Dependencies</h4>
        {incoming.length === 0 && outgoing.length === 0 && (
          <p className="text-xs text-ink-muted">none — this agent works on its own</p>
        )}
        {incoming.map((edge) => (
          <DependencyRow
            key={`in-${edge.from}`}
            label={`waits for ${roleOf(edge.from)}`}
            onRemove={() => onDisconnect(edge)}
          />
        ))}
        {outgoing.map((edge) => (
          <DependencyRow
            key={`out-${edge.to}`}
            label={`hands to ${roleOf(edge.to)}`}
            onRemove={() => onDisconnect(edge)}
          />
        ))}
      </section>

      <button
        type="button"
        onClick={onRemove}
        className="mt-auto cursor-pointer rounded border border-critical px-2 py-1 text-xs text-critical hover:bg-panel-strong"
      >
        Remove agent
      </button>
    </div>
  );
}

function DependencyRow({ label, onRemove }: { label: string; onRemove(): void }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-ink">
      <span>{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove dependency: ${label}`}
        className="cursor-pointer rounded border border-border px-1.5 py-0.5 text-ink-muted hover:bg-panel-strong"
      >
        Remove
      </button>
    </div>
  );
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs uppercase tracking-wide text-ink-faint">
        {label}
      </label>
      {children}
    </div>
  );
}
