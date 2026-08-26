import type {
  TeamAgent,
  TeamDefinition,
  TeamDependency,
  TeamTradingLimits,
} from "./teamsApi";

/**
 * Editing a definition as plain functions over a plain value, each returning a new one so the editor can tell
 * whether anything is unsaved. Validity is the module's answer; the two exceptions below are canvas hygiene.
 */

export const NEW_AGENT_ROLE = "New role";

/** A key nothing in this draft uses. `agent-1`, `agent-2`, … — an identifier, never
 *  shown to the operator, who reads the role instead. */
export function nextAgentKey(definition: TeamDefinition): string {
  const taken = new Set(definition.agents.map((agent) => agent.key));
  for (let n = 1; ; n += 1) {
    const candidate = `agent-${n}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/**
 * A team with one agent on it. `modelId` comes from the module's catalogue, never from a constant here: the
 * terminal carries no model id of its own (specs/teams-models).
 */
export function emptyDefinition(modelId: string): TeamDefinition {
  return {
    agents: [newAgent("agent-1", modelId)],
    dependencies: [],
    limits: { runLimit: null, dailyLimit: null },
    // Three empty trading limits, which is a team allowed to trade without one — the module holds no default
    // and puts no ceiling in for a missing one (specs/teams-trading, "Każda granica…daje się wyłączyć").
    trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
  };
}

function newAgent(key: string, modelId: string): TeamAgent {
  return { key, role: NEW_AGENT_ROLE, prompt: "", guidance: "", modelId, tools: [] };
}

export function addAgent(definition: TeamDefinition, modelId: string): TeamDefinition {
  return {
    ...definition,
    agents: [...definition.agents, newAgent(nextAgentKey(definition), modelId)],
  };
}

/** Removes the agent and every dependency touching it — an edge to a role that is gone
 *  is not a dependency the module would take, and leaving it on the canvas would make
 *  the refusal arrive from the server for something the operator already did. */
export function removeAgent(definition: TeamDefinition, key: string): TeamDefinition {
  return {
    ...definition,
    agents: definition.agents.filter((agent) => agent.key !== key),
    dependencies: definition.dependencies.filter(
      (edge) => edge.from !== key && edge.to !== key,
    ),
  };
}

export function updateAgent(
  definition: TeamDefinition,
  key: string,
  patch: Partial<Omit<TeamAgent, "key">>,
): TeamDefinition {
  return {
    ...definition,
    agents: definition.agents.map((agent) =>
      agent.key === key ? { ...agent, ...patch } : agent,
    ),
  };
}

/** One trading limit changed, the other two left alone. An empty field is `null` — no
 *  limit — and never a zero: the module refuses a zero outright, because a team that may
 *  place no orders is a team whose agents carry no write tools, and the two say different
 *  things. */
export function setTradingLimit(
  definition: TeamDefinition,
  patch: Partial<TeamTradingLimits>,
): TeamDefinition {
  return { ...definition, trading: { ...definition.trading, ...patch } };
}

export function addDependency(
  definition: TeamDefinition,
  edge: TeamDependency,
): TeamDefinition {
  if (edge.from === edge.to) return definition;
  if (hasDependency(definition, edge)) return definition;
  return { ...definition, dependencies: [...definition.dependencies, edge] };
}

export function removeDependency(
  definition: TeamDefinition,
  edge: TeamDependency,
): TeamDefinition {
  return {
    ...definition,
    dependencies: definition.dependencies.filter(
      (existing) => !(existing.from === edge.from && existing.to === edge.to),
    ),
  };
}

export function hasDependency(definition: TeamDefinition, edge: TeamDependency): boolean {
  return definition.dependencies.some(
    (existing) => existing.from === edge.from && existing.to === edge.to,
  );
}

/** Whether anything about the draft differs from what was last saved. Compared by value
 *  rather than by a dirty flag, so undoing an edit by hand — retyping the old role —
 *  leaves the Save button as quiet as it was. */
export function hasChanges(draft: TeamDefinition, saved: TeamDefinition): boolean {
  return JSON.stringify(draft) !== JSON.stringify(saved);
}

/**
 * One column per dependency depth, so the direction of work reads left to right without clicking. A cycle would
 * make depth infinite, so the walk stops at the first repeat and leaves the rest where they last landed.
 */
export function layout(definition: TeamDefinition): Map<string, { x: number; y: number }> {
  const depth = new Map<string, number>();
  for (const agent of definition.agents) depth.set(agent.key, 0);

  // One pass per agent is enough for the longest acyclic path; a draft still carrying a cycle simply stops
  // improving after that, which is the "leaves the rest where they are" case above.
  for (let pass = 0; pass < definition.agents.length; pass += 1) {
    let moved = false;
    for (const edge of definition.dependencies) {
      const from = depth.get(edge.from);
      const to = depth.get(edge.to);
      if (from === undefined || to === undefined) continue;
      if (to < from + 1) {
        depth.set(edge.to, from + 1);
        moved = true;
      }
    }
    if (!moved) break;
  }

  const perColumn = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const agent of definition.agents) {
    const column = depth.get(agent.key) ?? 0;
    const row = perColumn.get(column) ?? 0;
    perColumn.set(column, row + 1);
    positions.set(agent.key, { x: column * 280, y: row * 160 });
  }
  return positions;
}
