/**
 * "A turn just ended" — announced once, listened to by whatever reads state the agent may
 * have written somewhere else.
 *
 * The chart already had its own answer to this: `syncChartCommands` runs after every turn
 * and pulls the commands and the drawings the agent left in `agent`'s own database
 * (`terminal-agent-chat`, "Panel mówi, że wykres zmienił agent"). What that mechanism
 * cannot cover is a tool that wrote into a **different module** — since `teams-mcp`, a
 * chat can create a team, revise it, run it and put it on a schedule, and none of that
 * passes through `agent` at all. The Teams tab read its catalogue once, on mount, so a
 * team created by the model existed everywhere except on the screen until the operator
 * pressed F5.
 *
 * Deliberately dumb: no payload, no tool names, no per-area channels. A terminal holding a
 * list of `teams-mcp`'s writing tools would be a second copy of that module's surface,
 * drifting from the first the day a tool is added — the same reason no picker here carries
 * its own list of models or tools (`terminal-teams`). A listener re-reads what it owns and
 * decides for itself whether anything changed; one `GET` per finished turn is cheaper than
 * being wrong about which turns mattered.
 *
 * What a listener MUST NOT do is overwrite something the operator is editing. The team
 * catalogue is a read and refreshes freely; a draft open on the canvas is not, and nothing
 * here touches it.
 */

export interface AgentActivityStore {
  /** Returns the unsubscribe. */
  subscribe(listener: () => void): () => void;
  turnFinished(): void;
}

export function createAgentActivityStore(): AgentActivityStore {
  const listeners = new Set<() => void>();

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    turnFinished(): void {
      // A copy, so a listener that unsubscribes while being notified — a tab unmounting
      // on the same event — does not shorten the set being walked. And each one's failure
      // is its own: a tab that throws must not stop the next tab from hearing this.
      for (const listener of [...listeners]) {
        try {
          listener();
        } catch {
          // Nothing to say here that the listener could not say itself; swallowing keeps
          // one stale tab from taking the rest down with it.
        }
      }
    },
  };
}

export const agentActivity = createAgentActivityStore();
