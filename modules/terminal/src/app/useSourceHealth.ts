import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { queryClient } from "../data/query";
import type { SourcePart } from "../data/source";
import { MarketDataError } from "../data/types";

export type SourceHealth = "checking" | "reachable" | "unreachable" | "signed-out";

/** A source that will not answer without a credential is not a source that is
 *  down. `types.ts` keeps `unauthenticated` apart from `unreachable` so that
 *  this indicator can too — and flattening the two here is what sent an
 *  operator through a night of Azure dashboards for an expired session, with
 *  both back ends healthy and answering the whole time. */
function healthFromFailure(cause: unknown): SourceHealth {
  return cause instanceof MarketDataError && cause.kind === "unauthenticated"
    ? "signed-out"
    : "unreachable";
}

const POLL_MS = 15_000;

/** Pings every part of the source on mount and every `POLL_MS` after —
 *  independent of whatever charts are or aren't subscribed, so the indicator in
 *  the top bar reflects the sources themselves, not one chart's luck.
 *  terminal-shell spec, "Stan źródła danych jest widoczny globalnie".
 *
 *  One query per part, because they fail separately and mean different things:
 *  the archive down empties the charts, the gateway down stops the search, and
 *  reporting either as "the source is unreachable" would send an operator
 *  looking in the wrong place (design.md, Risks). */
export function useSourceHealth(parts: readonly SourcePart[]): Record<string, SourceHealth> {
  const results = useQueries(
    {
      queries: parts.map((part) => ({
        queryKey: ["source-health", part.id],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          await part.ping(signal);
          return "reachable" as const;
        },
        refetchInterval: POLL_MS,
      })),
    },
    queryClient,
  );

  const health = parts.map((part, index): [string, SourceHealth] => {
    const result = results[index];
    if (result.isSuccess) return [part.id, "reachable"];
    if (result.isError) return [part.id, healthFromFailure(result.error)];
    return [part.id, "checking"];
  });

  // Keyed on the values, not on the array `useQueries` rebuilds every render: the top
  // bar re-renders on every parent render either way, but a new record identity would
  // also restart any effect downstream that watches this.
  const signature = health.map(([id, state]) => `${id}:${state}`).join("|");
  return useMemo(() => Object.fromEntries(health), [signature]); // eslint-disable-line react-hooks/exhaustive-deps
}
