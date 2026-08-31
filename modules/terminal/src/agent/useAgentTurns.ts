import { useEffect, useRef } from "react";
import { agentActivity, type AgentActivityStore } from "./agentActivity";

/**
 * Runs `onFinished` after every agent turn. The callback is held in a ref rather than listed as a dependency: an
 * inline arrow resubscribes on every render, and a subscription that churns can miss the event it exists for.
 */
export function useAgentTurns(
  onFinished: () => void,
  store: AgentActivityStore = agentActivity,
): void {
  const latest = useRef(onFinished);
  latest.current = onFinished;

  useEffect(() => store.subscribe(() => latest.current()), [store]);
}
