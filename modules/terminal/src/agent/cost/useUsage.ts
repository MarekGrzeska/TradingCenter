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
 * The range is part of the cache key, so switching back renders what is known while the fresh answer arrives. Unlike
 * `useJobHistory`, a failure clears `summary`: a stale cost read as current is what this tab exists to prevent.
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
