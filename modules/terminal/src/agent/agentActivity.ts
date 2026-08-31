/**
 * "A turn just ended", announced once for whatever reads state the agent may have written elsewhere. Deliberately
 * dumb — a terminal holding a list of another module's writing tools is a copy of its surface, drifting.
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
      // A copy, so a listener that unsubscribes while being notified does not shorten the set being
      // walked. And each one's failure is its own: a tab that throws must not silence the next.
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
