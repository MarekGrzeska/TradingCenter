import { useCallback, useEffect, useState } from "react";
import type { TeamsApi, TeamSummary, TeamsModel, TeamsTool } from "./teamsApi";

export type LoadStatus = "loading" | "ready" | "error";

/** One read, once, with a way to ask again — the shape every hook here has. */
interface Loaded<T> {
  status: LoadStatus;
  value: T;
  error: string | null;
  reload(): void;
}

function useLoaded<T>(
  read: (signal: AbortSignal) => Promise<T>,
  initial: T,
  fallbackMessage: string,
): Loaded<T> {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [value, setValue] = useState<T>(initial);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");
    setError(null);

    read(controller.signal)
      .then((answer) => {
        if (cancelled) return;
        setValue(answer);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : fallbackMessage);
        setStatus("error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // `read` is rebuilt per render by every caller below; `attempt` is the real trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  return { status, value, error, reload: useCallback(() => setAttempt((n) => n + 1), []) };
}

export function useTeams(api: TeamsApi): Loaded<TeamSummary[]> {
  return useLoaded(
    useCallback((signal: AbortSignal) => api.listTeams(signal), [api]),
    [],
    "could not read the team catalogue",
  );
}

/**
 * What the pickers in the agent panel are built from: the module's model catalogue and
 * whatever its tool server announces. Neither list is ever written down in this
 * terminal (`terminal-teams`, "terminal MUST NOT nieść własnej listy jednych ani
 * drugich") — which is also why the editor waits for the models to arrive before it
 * opens a team at all: a new agent needs a model id, and the only place to get one is
 * here.
 */
export function useModels(api: TeamsApi): Loaded<TeamsModel[]> {
  return useLoaded(
    useCallback((signal: AbortSignal) => api.listModels(signal), [api]),
    [],
    "could not read the model catalogue",
  );
}

export function useTools(api: TeamsApi): Loaded<TeamsTool[]> {
  return useLoaded(
    useCallback((signal: AbortSignal) => api.listTools(signal), [api]),
    [],
    "could not read the tool list",
  );
}
