import { useEffect, useState } from "react";
import type { SourcePart } from "../data/source";

export type SourceHealth = "checking" | "reachable" | "unreachable";

const POLL_MS = 15_000;

/** Pings every part of the source on mount and every `POLL_MS` after —
 *  independent of whatever charts are or aren't subscribed, so the indicator in
 *  the top bar reflects the sources themselves, not one chart's luck.
 *  terminal-shell spec, "Stan źródła danych jest widoczny globalnie".
 *
 *  One state per part, because they fail separately and mean different things:
 *  the archive down empties the charts, the gateway down stops the search, and
 *  reporting either as "the source is unreachable" would send an operator
 *  looking in the wrong place (design.md, Risks). */
export function useSourceHealth(parts: readonly SourcePart[]): Record<string, SourceHealth> {
  const [health, setHealth] = useState<Record<string, SourceHealth>>(() =>
    Object.fromEntries(parts.map((part) => [part.id, "checking" as SourceHealth])),
  );

  useEffect(() => {
    let cancelled = false;
    let inFlight: AbortController | null = null;
    setHealth(Object.fromEntries(parts.map((part) => [part.id, "checking" as SourceHealth])));

    function check() {
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      for (const part of parts) {
        part
          .ping(controller.signal)
          .then(() => {
            if (!cancelled) setHealth((prev) => ({ ...prev, [part.id]: "reachable" }));
          })
          .catch(() => {
            if (!cancelled && !controller.signal.aborted) {
              setHealth((prev) => ({ ...prev, [part.id]: "unreachable" }));
            }
          });
      }
    }

    check();
    const interval = setInterval(check, POLL_MS);

    return () => {
      cancelled = true;
      inFlight?.abort();
      clearInterval(interval);
    };
  }, [parts]);

  return health;
}
