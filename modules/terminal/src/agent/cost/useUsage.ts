import { useCallback, useEffect, useState } from "react";
import type { AgentApi, AgentUsageSummary, UsageRange } from "../agentApi";

export type UsageStatus = "loading" | "ready" | "unreachable";

export interface UsageState {
  status: UsageStatus;
  summary: AgentUsageSummary | null;
  error: string | null;
  reload(): void;
}

/**
 * Reads `GET /usage` for one range, refetching whenever the range changes.
 *
 * Deliberately unlike `useJobHistory`: there, a failed poll keeps the last good rows
 * on screen with a warning, because a job's history was already known and a page
 * still describes it. Here a failure clears `summary` instead — `terminal-agent-cost`
 * spec, "MUST NOT pokazywać liczb sprzed awarii jako bieżących". A stale cost read as
 * current is exactly the failure this tab exists to keep from happening; the other
 * tab's gentler pattern would reproduce it.
 */
export function useUsage(api: AgentApi, range: UsageRange): UsageState {
  const [summary, setSummary] = useState<AgentUsageSummary | null>(null);
  const [status, setStatus] = useState<UsageStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");

    api
      .usage(range, controller.signal)
      .then((next) => {
        if (cancelled) return;
        setSummary(next);
        setStatus("ready");
        setError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setSummary(null);
        setError(cause instanceof Error ? cause.message : "could not read usage");
        setStatus("unreachable");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- range's identity changes every render; its two fields are the real dependency.
  }, [api, range.from, range.to, attempt]);

  return { status, summary, error, reload };
}
