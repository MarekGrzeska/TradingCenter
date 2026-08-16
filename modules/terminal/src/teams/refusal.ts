import type { TeamDefinition, TeamDependency } from "./teamsApi";

/**
 * Where on the canvas a refusal belongs.
 *
 * The module refuses a definition by naming what is wrong with it — the agent whose
 * model is not in the catalogue, the agents a cycle runs through, the one wired to
 * nothing (specs/teams-catalogue, "Odmowa MUST nazywać agenta albo zależność, przez
 * którą zapadła"). Showing that message alone in a corner of the screen throws that away
 * again: "definition invalid" against eight roles is the operator searching by hand for
 * what the module already knows (`terminal-teams`, "Zapis odrzucony przez moduł jest
 * pokazany przy miejscu, którego dotyczy").
 *
 * So this reads the keys back out of the message. Quoted only — `'scout'`, or inside a
 * Python list as `['scout', 'judge']` — which is how every refusal in `teams/
 * validation.py` and `teams/contract.py` spells one, and which cannot match `agent-10`
 * when the message names `agent-1`.
 *
 * A message naming nothing this draft knows leaves `agents` empty, and the editor shows
 * it as it arrived. The message is never replaced by this side's own words: whatever
 * the module said is the operator's whole lead.
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

  // Both ends, not either: an edge sharing one end with a named agent is the neighbour
  // of the problem, not the problem. A cycle names every agent on it, so its edges are
  // exactly the ones with both ends inside that set.
  const dependencies = definition.dependencies.filter(
    (edge) => named.has(edge.from) && named.has(edge.to),
  );

  return { message, agents, dependencies };
}
