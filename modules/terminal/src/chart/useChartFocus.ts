import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { IChartApi } from "lightweight-charts";
import type { Time } from "lightweight-charts";
import type { Bar, ChartFocusRequest, Resolution } from "../data/types";
import { showToast } from "../ui/toastStore";
import {
  focusNeedsBackTo,
  nearestBarIndex,
  overlapsSeries,
  reachesBack,
} from "./chartWindow";

export interface ChartFocusInput {
  symbol: string;
  resolution: Resolution;
  focusRequest: ChartFocusRequest | null;
  onFocusRequestSettled: (() => void) | undefined;
  chartRef: RefObject<IChartApi | null>;
  barsRef: RefObject<Bar[]>;
  /** The pager's two doors, filled by the chart after `useOlderBars` has returned: walk
   *  back a page at a time, or read straight to a named moment. */
  requestOlderRef: RefObject<() => void>;
  reachBackRef: RefObject<(target: number) => void>;
}

export interface ChartFocus {
  /** What is currently being pursued. A ref rather than state because the three callers
   *  that read it — a page landing, the pager asking whether it needs more, a history
   *  read finishing — all run outside React. */
  pendingFocusRef: RefObject<ChartFocusRequest | null>;
  pursueFocus: (focus: ChartFocusRequest) => void;
  settlePendingFocus: (focus: ChartFocusRequest) => void;
  /** A focus pursued for a series that is about to be cleared: abandoned rather than
   *  retried against whatever loads next, and the caller told, the same as any other
   *  settled request. */
  abandonPendingFocus: () => void;
}

/**
 * A one-off "show this fragment" arriving from outside, and the paging it needs to become
 * showable.
 *
 * Its own file because it is a machine with one entry and one exit — a request comes in,
 * and exactly one settlement goes back out however it ends — wound through parts of the
 * chart that have nothing else to do with it. Keeping it whole is what makes "every
 * request is settled exactly once" readable in one place instead of five.
 */
export function useChartFocus({
  symbol,
  resolution,
  focusRequest,
  onFocusRequestSettled,
  chartRef,
  barsRef,
  requestOlderRef,
  reachBackRef,
}: ChartFocusInput): ChartFocus {
  // What is currently being pursued — set the moment a request cannot be shown yet,
  // cleared the moment it settles one way or the other. Read by `needsMore` below, which
  // is how a single `requestOlder()` call ends up paging until this is satisfied or the
  // pager gives up on its own (design.md, "Dociąganie pod kadr przez istniejący pager").
  const pendingFocusRef = useRef<ChartFocusRequest | null>(null);
  const onFocusRequestSettledRef = useRef(onFocusRequestSettled);
  onFocusRequestSettledRef.current = onFocusRequestSettled;

  const applyFocusToView = useCallback((focus: ChartFocusRequest): boolean => {
    const chart = chartRef.current;
    const series = barsRef.current;
    if (!chart || !overlapsSeries(series, focus)) return false;
    const timeScale = chart.timeScale();
    if (focus.lastBars !== null) {
      const shown = Math.min(focus.lastBars, series.length);
      timeScale.setVisibleLogicalRange({ from: series.length - shown, to: series.length - 1 });
      return true;
    }
    if (focus.from !== null && focus.to !== null) {
      timeScale.setVisibleRange({ from: focus.from as Time, to: focus.to as Time });
      return true;
    }
    // The one shape left: `around` + `bars`, checked exactly one way by the module that
    // wrote this request — `around` and `bars` are never null here.
    const index = nearestBarIndex(series, focus.around as number);
    const bars = focus.bars as number;
    const from = index - Math.floor(bars / 2);
    timeScale.setVisibleLogicalRange({ from, to: from + bars - 1 });
    return true;
  }, [chartRef, barsRef]);

  /** The one place a pursuit ends, however it ends: applies `focus` against whatever is
   *  now drawn (which may be all of it, some of it, or — if nothing overlaps — none),
   *  clears it as the pending one, and always tells the caller it is done. An application
   *  that touched nothing is reported the way an unreadable indicator already is
   *  (`terminal-chart` spec, "say it, do not hide it" — the same rule this file already
   *  follows for indicators it could not compute). */
  const settlePendingFocus = useCallback(
    (focus: ChartFocusRequest) => {
      pendingFocusRef.current = null;
      const applied = applyFocusToView(focus);
      onFocusRequestSettledRef.current?.();
      if (!applied) {
        showToast({
          key: `focus:${symbol}:${resolution}`,
          severity: "error",
          title: `${symbol} · requested focus is outside the archive`,
          detail: "The archive has no candles there right now.",
        });
      }
    },
    [applyFocusToView, symbol, resolution],
  );

  /** Applies `focus` now if the series already reaches back far enough; otherwise asks
   *  the archive for what is missing and waits.
   *
   *  A focus that names a moment is fetched in one read of exactly the window between
   *  that moment and the oldest drawn bar (`reachBack`) — not walked to by the pager,
   *  which moves about a day of calendar per page on MINUTE_5 and stops after twenty of
   *  them. Walking is right for a drag to the left edge, where the destination is "a bit
   *  more"; it is wrong for "the middle of March", where the destination is known before
   *  the first request and five months away.
   *
   *  `lastBars` names no moment and keeps the walk: it wants more of the newest end, which
   *  is what the pager's own margin is already for. */
  const pursueFocus = useCallback(
    (focus: ChartFocusRequest) => {
      if (reachesBack(barsRef.current, focus)) {
        settlePendingFocus(focus);
        return;
      }
      pendingFocusRef.current = focus;
      const target = focusNeedsBackTo(focus, resolution);
      if (target === null) requestOlderRef.current();
      else reachBackRef.current(target);
    },
    [settlePendingFocus, resolution, barsRef, requestOlderRef, reachBackRef],
  );

  useEffect(() => {
    if (focusRequest) pursueFocus(focusRequest);
  }, [focusRequest, pursueFocus]);

  const abandonPendingFocus = useCallback(() => {
    if (pendingFocusRef.current) {
      pendingFocusRef.current = null;
      onFocusRequestSettledRef.current?.();
    }
  }, []);

  return { pendingFocusRef, pursueFocus, settlePendingFocus, abandonPendingFocus };
}
