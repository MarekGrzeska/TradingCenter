import { useRead } from "../../data/query";
import type { AgentApi, AgentPrompt } from "../agentApi";

export type PromptStatus = "loading" | "ready" | "unreachable";

export interface PromptState {
  status: PromptStatus;
  prompt: AgentPrompt | null;
  error: string | null;
  reload(): void;
}

/**
 * Reads `GET /prompt` once per mount — the section unmounts its body on collapse, so re-expanding is what
 * re-reads. `onFailure: "forget"`, because the prompt on screen is what the operator is about to edit.
 */
export function usePrompt(api: AgentApi): PromptState {
  const read = useRead<AgentPrompt | null>({
    key: ["agent", "prompt"],
    read: (signal) => api.getPrompt(signal),
    initial: null,
    fallbackMessage: "could not read the prompt",
    onFailure: "forget",
  });

  return {
    status: read.status === "error" ? "unreachable" : read.status,
    prompt: read.value,
    error: read.error,
    reload: read.reload,
  };
}
