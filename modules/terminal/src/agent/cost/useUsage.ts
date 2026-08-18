import { useRead } from "../../data/query";
import type { AgentApi, AgentUsageSummary, UsageRange } from "../agentApi";

export type UsageStatus = "loading" | "ready" | "unreachable";

export interface UsageState {
  status: UsageStatus;
  summary: AgentUsageSummary | null;
  error: string | null;
  reload(): void;
}

/**
 * Reads `GET /usage` for one range, refetching whenever the range changes — the range
 * is part of the cache key, so switching back to a range already read renders it while
 * the fresh answer is on its way.
 *
 * Deliberately unlike `useJobHistory`: there, a failed poll keeps the last good rows
 * on screen with a warning, because a job's history was already known and a page
 * still describes it. Here a failure clears `summary` instead — `terminal-agent-cost`
 * spec, "MUST NOT pokazywać liczb sprzed awarii jako bieżących". A stale cost read as
 * current is exactly the failure this tab exists to keep from happening; the other
 * tab's gentler pattern would reproduce it. That is what `onFailure: "forget"` says.
 */
export function useUsage(api: AgentApi, range: UsageRange): UsageState {
  const read = useRead<AgentUsageSummary | null>({
    key: ["agent", "usage", range.from, range.to],
    read: (signal) => api.usage(range, signal),
    initial: null,
    fallbackMessage: "could not read usage",
    onFailure: "forget",
  });

  return {
    status: read.status === "error" ? "unreachable" : read.status,
    summary: read.value,
    error: read.error,
    reload: read.reload,
  };
}
