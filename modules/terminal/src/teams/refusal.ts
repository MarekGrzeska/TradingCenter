import type { TeamDefinition, TeamDependency } from "./teamsApi";

/**
 * The module refuses by naming what is wrong, so the message is read for keys and shown at the place it names
 * (`terminal-teams`). Quoted forms only — `'scout'` — which cannot match `agent-10` when the message says `agent-1`.
 */

export interface Refusal {
  /** The module's own message, unchanged. */
  message: string;
  /** Keys of the agents it names, in the draft's own order. */
  agents: string[];
  /** Dependencies both of whose ends it names — a cycle's edges, chiefly. */
  dependencies: TeamDependency[];
}

function namesKey(message: string, key: string): boolean {
  return message.includes(`'${key}'`) || message.includes(`"${key}"`);
}

export function locateRefusal(message: string, definition: TeamDefinition): Refusal {
  const agents = definition.agents
    .map((agent) => agent.key)
    .filter((key) => namesKey(message, key));
  const named = new Set(agents);

  // Both ends, not either: an edge sharing one end with a named agent is the neighbour of the problem. A
  // cycle names every agent on it, so its edges are exactly those with both ends inside that set.
  const dependencies = definition.dependencies.filter(
    (edge) => named.has(edge.from) && named.has(edge.to),
  );

  return { message, agents, dependencies };
}
