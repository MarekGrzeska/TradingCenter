import { useState } from "react";
import { ModalShell } from "../ui/ModalShell";
import type { Refusal } from "./refusal";
import type { TeamAgent, TeamDefinition, TeamDependency, TeamsModel, TeamsTool } from "./teamsApi";
import { Button } from "../ui/Button";

/**
 * One agent's settings, opened from the gear on its own box on the canvas.
 *
 * This was a 20rem column beside the canvas, and the prompt is what paid for it: the field
 * an operator writes the most in had five rows and no width, while the tool list underneath
 * it scrolled the whole panel away. A modal is not a second view — the graph stays behind
 * it, so the requirement this has to keep holding still holds (`terminal-teams`, "Operator
 * składa zespół w tym samym widoku, w którym go ogląda").
 *
 * Two columns, and the split is by how much room each thing needs rather than by kind:
 * everything that is a choice (role, model, tools, dependencies) reads down the left,
 * while the prompt takes the whole right side and grows with the dialog.
 *
 * Both pickers are built from what the module publishes — `models` from its catalogue,
 * `tools` from what its tool server announces — and this file names no model and no tool
 * of its own. That is the requirement, not an implementation detail: adding a model is a
 * line in the module's configuration, and a terminal carrying its own list would make it
 * a release here too.
 *
 * Nothing here is saved by closing it. Every keystroke edits the draft the canvas and the
 * Save button already share, so `Done` means "I am finished looking at this agent" and the
 * revision is still saved from the editor's own header.
 */
export function AgentSettingsDialog({
  agent,
  definition,
  models,
  tools,
  toolsNote,
  refusal,
  onChange,
  onClose,
  onRemove,
  onConnect,
  onDisconnect,
}: {
  agent: TeamAgent;
  definition: TeamDefinition;
  models: TeamsModel[];
  tools: TeamsTool[];
  /** Why the tool list is empty, when it is — an unreachable or unconfigured tool server
   *  is a working state, and the dialog says which rather than showing an empty box. */
  toolsNote: string | null;
  refusal: Refusal | null;
  onChange(patch: Partial<Omit<TeamAgent, "key">>): void;
  onClose(): void;
  onRemove(): void;
  onConnect(edge: TeamDependency): void;
  onDisconnect(edge: TeamDependency): void;
}) {
  const [waitFor, setWaitFor] = useState("");
  const incoming = definition.dependencies.filter((edge) => edge.to === agent.key);
  const outgoing = definition.dependencies.filter((edge) => edge.from === agent.key);
  // Itself excluded, and so is anything it already waits for. An agent it hands to is left
  // in: the module refuses a cycle by name, and hiding the option would replace a refusal
  // that says which agents are on the cycle with a list that quietly lacks one.
  const available = definition.agents.filter(
    (candidate) =>
      candidate.key !== agent.key && !incoming.some((edge) => edge.from === candidate.key),
  );
  const roleOf = (key: string) =>
    definition.agents.find((candidate) => candidate.key === key)?.role ?? key;
  const refusedHere = refusal?.agents.includes(agent.key) ?? false;
  // A model that was in the catalogue when the revision was saved and is not now still
  // has to appear in the picker — otherwise selecting nothing silently rewrites the
  // agent onto whatever sits first in the list.
  const modelMissing = !models.some((model) => model.id === agent.modelId);

  return (
    <ModalShell
      title={`Agent: ${agent.role}`}
      size="wide"
      showCloseButton
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <Button
            tone="critical"
            onClick={onRemove}
          >
            Remove agent
          </Button>
          <Button
            tone="primary"
            size="md"
            onClick={onClose}
          >
            Done
          </Button>
        </div>
      }
    >
      {refusedHere && refusal && (
        <p className="mb-3 rounded border border-critical bg-panel px-2 py-1 text-xs text-critical">
          {refusal.message}
        </p>
      )}

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[18rem_1fr]">
        <div className="flex min-h-0 flex-col gap-3 overflow-auto md:border-r md:border-border md:pr-4">
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

          <fieldset className="flex flex-col gap-1">
            <legend className="text-xs uppercase tracking-wide text-ink-faint">Tools</legend>
            {tools.length === 0 ? (
              <p className="text-xs text-ink-muted">
                {toolsNote ?? "the module announces no tools"}
              </p>
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
                    <ToolMark readOnly={tool.readOnly} />
                    {tool.description && (
                      <span className="block text-ink-faint">{tool.description}</span>
                    )}
                  </span>
                </label>
              ))
            )}
            {/* Assigned by a revision saved earlier, and no longer announced. Left visible
                and removable rather than dropped quietly: this is what will refuse the next
                run (specs/teams-tool-access, "Narzędzie znika po stronie serwera"). */}
            {agent.tools
              .filter((name) => !tools.some((tool) => tool.name === name))
              .map((name) => (
                <label key={name} className="flex items-center gap-2 text-xs text-critical">
                  <input
                    type="checkbox"
                    checked
                    onChange={() =>
                      onChange({ tools: agent.tools.filter((tool) => tool !== name) })
                    }
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
            {/* The second way to draw an edge, and the one that works without a mouse.
                Dragging between two handles on the canvas is the direct way and stays the
                direct way; this exists because a dependency is a choice of agent, and
                choosing an agent from a list of them is a thing a list is good at. */}
            {available.length > 0 && (
              <div className="mt-1 flex items-center gap-1">
                <label htmlFor="agent-waits-for" className="sr-only">
                  Waits for
                </label>
                <select
                  id="agent-waits-for"
                  value={waitFor}
                  onChange={(event) => setWaitFor(event.target.value)}
                  className="min-w-0 flex-1 rounded border border-border bg-panel px-2 py-1 text-xs text-ink"
                >
                  <option value="">waits for…</option>
                  {available.map((candidate) => (
                    <option key={candidate.key} value={candidate.key}>
                      {candidate.role}
                    </option>
                  ))}
                </select>
                <Button
                  disabled={waitFor === ""}
                  onClick={() => {
                    onConnect({ from: waitFor, to: agent.key });
                    setWaitFor("");
                  }}
                >
                  Add
                </Button>
              </div>
            )}
          </section>
        </div>

        {/* The reason this dialog exists. The prompt takes whatever height the dialog has
            left over; the guidance is a note about how to answer, and stays a note. */}
        <div className="flex min-h-0 flex-col gap-3">
          <div className="flex min-h-0 flex-1 flex-col gap-1">
            <label
              htmlFor="agent-prompt"
              className="text-xs uppercase tracking-wide text-ink-faint"
            >
              Prompt
            </label>
            <textarea
              id="agent-prompt"
              value={agent.prompt}
              onChange={(event) => onChange({ prompt: event.target.value })}
              className="min-h-40 w-full flex-1 resize-none rounded border border-border bg-panel px-2 py-1 font-mono text-xs text-ink"
            />
          </div>

          <Field id="agent-guidance" label="Guidance">
            <textarea
              id="agent-guidance"
              rows={4}
              value={agent.guidance}
              onChange={(event) => onChange({ guidance: event.target.value })}
              className="w-full resize-none rounded border border-border bg-panel px-2 py-1 font-mono text-xs text-ink"
            />
          </Field>
        </div>
      </div>
    </ModalShell>
  );
}

/**
 * What ticking this tool lets the agent do to the account.
 *
 * Marked, rather than sorted into two lists: an operator picking tools reads them by what
 * they do, and splitting the picker would put the one tool that matters at the bottom of
 * a scroll (`terminal-teams`, "narzędzia zmieniające stan rachunku są odróżnione od
 * czytających").
 *
 * Three states, not two. A tool the server annotates as read-only gets no mark at all —
 * reading is what a tool does unless somebody says otherwise — while one carrying no
 * annotation is shown as exactly that. Both of this module's tool servers annotate
 * everything they publish, so an unmarked-and-unannotated tool means a third server
 * nobody here has an opinion about (specs/teams-tool-access).
 */
function ToolMark({ readOnly }: { readOnly: boolean | null }) {
  if (readOnly === true) return null;
  return readOnly === false ? (
    <span className="ml-1 rounded border border-warning px-1 text-[0.65rem] uppercase text-warning">
      moves the account
    </span>
  ) : (
    <span className="ml-1 text-[0.65rem] uppercase text-ink-faint">unannotated</span>
  );
}

function DependencyRow({ label, onRemove }: { label: string; onRemove(): void }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-ink">
      <span>{label}</span>
      <Button
        tone="muted"
        size="xs"
        onClick={onRemove}
        aria-label={`Remove dependency: ${label}`}
      >
        Remove
      </Button>
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
