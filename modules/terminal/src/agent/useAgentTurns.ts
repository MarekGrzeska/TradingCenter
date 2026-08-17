import { useEffect, useRef } from "react";
import { agentActivity, type AgentActivityStore } from "./agentActivity";

/**
 * Runs `onFinished` after every agent turn, for a view showing state a chat can change
 * from outside it (`agentActivity.ts`).
 *
 * The callback is held in a ref rather than listed as a dependency: a caller passing an
 * inline arrow would otherwise resubscribe on every render, and a subscription that churns
 * every render is one that can miss the event it exists for.
 */
export function useAgentTurns(
  onFinished: () => void,
  store: AgentActivityStore = agentActivity,
): void {
  const latest = useRef(onFinished);
  latest.current = onFinished;

  useEffect(() => store.subscribe(() => latest.current()), [store]);
}
