import { useEffect, useRef, useState } from "react";
import type { IndicatorSource } from "../../data/source";
import type { IndicatorResult, IndicatorSelection, Resolution } from "../../data/types";

export type IndicatorsStatus = "idle" | "loading" | "ready" | "error";

export interface IndicatorsState {
  status: IndicatorsStatus;
  times: number[];
  results: IndicatorResult[];
  /** The selections these results were computed for, in the order they were asked for. Kept beside the
   *  results rather than read from current state: while a read is in flight the operator may already have
   *  added an instance, and zipping fresh selections onto stale results would mislabel every one. */
  selections: IndicatorSelection[];
  error: string | null;
  retry(): void;
}

export interface BarsRange {
  from: number;
  to: number;
}

const IDLE: IndicatorsState = {
  status: "idle",
  times: [],
  results: [],
  selections: [],
  error: null,
  retry: () => {},
};

/**
 * The chosen indicators over whatever range the chart has candles for, recomputed when that range changes
 * structurally rather than on every tick. A failed compute never touches what candles are on screen.
 */
export function useIndicators(
  source: IndicatorSource | undefined,
  symbol: string,
  resolution: Resolution,
  selections: IndicatorSelection[],
  range: BarsRange | null,
): IndicatorsState {
  const [state, setState] = useState<IndicatorsState>(IDLE);
  const [attempt, setAttempt] = useState(0);

  // What actually changes the answer: which instances were asked for, and with what params. Colour is
  // deliberately not in here — refetching for it would make choosing a colour cost a read.
  const specsKey = selections
    .map((s) => `${s.key}|${s.id}|${JSON.stringify(s.params)}`)
    .join(";");
  const selectionsRef = useRef(selections);
  selectionsRef.current = selections;

  useEffect(() => {
    const selections = selectionsRef.current;
    if (!source || selections.length === 0 || range === null) {
      setState(IDLE);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, status: "loading", error: null }));

    source
      .computeIndicators(symbol, resolution, range.from, range.to, selections, controller.signal)
      .then((computed) => {
        if (cancelled) return;
        setState({
          status: "ready",
          times: computed.times,
          results: computed.results,
          selections,
          error: null,
          retry: () => setAttempt((n) => n + 1),
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // The last good answer stays on screen, and it keeps the selections it was computed for: the two
        // are one snapshot, and carrying half of it forward is the mislabelling this field prevents.
        setState((prev) => ({
          status: "error",
          times: prev.times,
          results: prev.results,
          selections: prev.selections,
          error: err instanceof Error ? err.message : "could not compute the selected indicators",
          retry: () => setAttempt((n) => n + 1),
        }));
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  // `range` relies on the caller keeping the reference stable across renders, which `Chart.tsx` does.
  // Selections come in through `specsKey`, so a change that cannot alter the answer costs no read.
  }, [source, symbol, resolution, range, specsKey, attempt]);

  return state;
}
