import { useCallback, useEffect, useState } from "react";
import type { AgentApi, AgentPrompt } from "../agentApi";

export type PromptStatus = "loading" | "ready" | "unreachable";

export interface PromptState {
  status: PromptStatus;
  prompt: AgentPrompt | null;
  error: string | null;
  reload(): void;
}

/**
 * Reads `GET /prompt` once per mount — `CollapsibleSection` unmounts its body on
 * collapse, so re-expanding is what re-reads, the same "ask the module, not memory"
 * shape `useUsage` uses for cost.
 */
export function usePrompt(api: AgentApi): PromptState {
  const [prompt, setPrompt] = useState<AgentPrompt | null>(null);
  const [status, setStatus] = useState<PromptStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");

    api
      .getPrompt(controller.signal)
      .then((next) => {
        if (cancelled) return;
        setPrompt(next);
        setStatus("ready");
        setError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setPrompt(null);
        setError(cause instanceof Error ? cause.message : "could not read the prompt");
        setStatus("unreachable");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, attempt]);

  return { status, prompt, error, reload };
}
