import { agentActivity, type AgentActivityStore } from "../agent/agentActivity";
import { agentApi, type AgentApi } from "../agent/agentApi";
import { createAgentChatStore, type AgentChatStore } from "../agent/agentChatStore";
import { strategyInView } from "../agent/strategyInView";

/**
 * The store behind the conversation beside a strategy's editor: the workbench's own conversation, on a store that keeps
 * nothing in `localStorage`, so the terminal's panel keeps its conversation and its collapse. Every turn carries the
 * strategy on screen, as the panel's do on this tab.
 */
export function createStrategyChatStore(activity: AgentActivityStore = agentActivity, api: AgentApi = agentApi): AgentChatStore {
  // No chart snapshot: the chart is not on this tab, and the question is about the strategy.
  return createAgentChatStore(null, api, undefined, () => null, undefined, activity, strategyInView);
}

