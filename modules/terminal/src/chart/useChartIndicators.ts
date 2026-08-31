import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import type { IChartApi } from "lightweight-charts";
import type { IndicatorSource } from "../data/source";
import type { Bar, IndicatorSelection, Resolution } from "../data/types";
import { showToast } from "../ui/toastStore";
import { readChartColors, type ChartColors } from "./theme";
import { assignLineColors, drawnInstances } from "./chartLines";
import { indicatorWindow, windowStillCovers } from "./chartWindow";
import {
  type BarsRange,
  type IndicatorsState,
  useIndicators,
} from "./indicators/useIndicators";
import {
  useIndicatorCatalogue,
  type IndicatorCatalogueState,
} from "./indicators/useIndicatorCatalogue";
import type { IndicatorCatalogueEntry } from "../data/types";

/** Asked for while the catalogue has not answered yet — one identity, so waiting for it
 *  costs no render of its own. */
const NO_SELECTIONS: IndicatorSelection[] = [];

export interface ChartIndicatorsInput {
  indicatorSource: IndicatorSource | undefined;
  symbol: string;
  resolution: Resolution;
  initialIndicatorSelections: IndicatorSelection[] | undefined;
  onIndicatorSelectionsChange: ((next: IndicatorSelection[]) => void) | undefined;
  /** The chart's own two refs, read rather than written: the window is whatever the time
   *  scale is showing over whatever the series holds, and both move without a render. */
  chartRef: RefObject<IChartApi | null>;
  barsRef: RefObject<Bar[]>;
  colorsRef: RefObject<ChartColors | null>;
}

export interface ChartIndicators {
  indicatorSelections: IndicatorSelection[];
  setIndicatorSelections: (next: IndicatorSelection[]) => void;
  catalogue: IndicatorCatalogueState;
  catalogueById: Map<string, IndicatorCatalogueEntry>;
  knownIndicatorSelections: IndicatorSelection[];
  unknownIndicatorIds: string[];
  indicatorsState: IndicatorsState;
  instanceColors: Map<string, string | null>;
  /** Shaped by the two functions that build it rather than restated here — the readout
   *  and the layers have to be given exactly what `assignLineColors` returns. */
  readoutAssignment: {
    drawn: ReturnType<typeof drawnInstances>;
    lineColors: ReturnType<typeof assignLineColors>;
  };
  failedIndicators: IndicatorsState["results"];
  failureDigest: string;
  /** Called from the chart's own handlers — a pan, a candle closing, a page of history
   *  landing — which run outside React, so the function has to be reachable through a ref
   *  that is always the current one. */
  syncIndicatorWindowRef: RefObject<(force?: boolean) => void>;
  /** What a symbol, resolution or source change owes the indicators: with no window there
   *  are no results, which the layer sync reads as "remove every line". */
  clearIndicatorWindow: () => void;
}

/**
 * The half of `Chart.tsx` with a boundary of its own: the chart's lifecycle writes candles into a canvas,
 * this reads what is on it and asks the archive. They meet at four places — two refs, the sync, the state.
 */
export function useChartIndicators({
  indicatorSource,
  symbol,
  resolution,
  initialIndicatorSelections,
  onIndicatorSelectionsChange,
  chartRef,
  barsRef,
  colorsRef,
}: ChartIndicatorsInput): ChartIndicators {
  const [indicatorSelections, setIndicatorSelectionsState] = useState<IndicatorSelection[]>(
    () => initialIndicatorSelections ?? [],
  );
  // A ref, not a dependency: notifying the caller must not itself be a reason
  // to redo anything below, only a side effect of the operator's own action.
  const onIndicatorSelectionsChangeRef = useRef(onIndicatorSelectionsChange);
  onIndicatorSelectionsChangeRef.current = onIndicatorSelectionsChange;
  const setIndicatorSelections = useCallback((next: IndicatorSelection[]) => {
    setIndicatorSelectionsState(next);
    onIndicatorSelectionsChangeRef.current?.(next);
  }, []);
  // The lazy `useState` initializer runs once at mount, so a later prop change stayed invisible until a
  // remount. Re-adopted when the prop is a *different* array — the operator's own edit round-trips the same one.
  useEffect(() => {
    if (initialIndicatorSelections === undefined) return;
    setIndicatorSelectionsState((current) =>
      current === initialIndicatorSelections ? current : initialIndicatorSelections,
    );
  }, [initialIndicatorSelections]);
  // Set from what `redraw` actually drew, not from every live tick, so an indicator does not refetch on
  // each forming-candle update (design.md's "na żywo" is a later stage; see `useIndicators`).
  const [barsRange, setBarsRange] = useState<BarsRange | null>(null);
  // What was last asked for, so a pan inside it costs nothing. State cannot answer this:
  // the range handler runs on every frame the library reports, long before a render.
  const heldIndicatorWindowRef = useRef<BarsRange | null>(null);

  /** Points the indicator window at what is on screen now, if what is on screen has left
   *  the window already computed. `force` for the structural changes that invalidate an
   *  answer whatever the frame is doing: a new period at the live edge, a series that
   *  just grew at the front. */
  const syncIndicatorWindow = useCallback(
    (force = false) => {
      const series = barsRef.current;
      const visible = chartRef.current?.timeScale().getVisibleLogicalRange() ?? null;
      const held = heldIndicatorWindowRef.current;
      if (!force && held !== null && windowStillCovers(held, series, visible)) return;
  // A fresh object even for an unchanged window is load-bearing: `useIndicators` watches `range` by
  // reference, and a candle closing must be recomputed over exactly the window already asked for.
      const next = indicatorWindow(series, visible, resolution);
      heldIndicatorWindowRef.current = next;
      setBarsRange(next);
    },
    [resolution, chartRef, barsRef],
  );
  const syncIndicatorWindowRef = useRef(syncIndicatorWindow);
  syncIndicatorWindowRef.current = syncIndicatorWindow;

  const catalogue = useIndicatorCatalogue(indicatorSource);
  const catalogueById = useMemo(
    () => new Map(catalogue.entries.map((entry) => [entry.id, entry] as const)),
    [catalogue.entries],
  );
  // A restored selection may name an indicator the catalogue no longer offers: dropped from what computes,
  // never rewritten in the caller's storage. Still-loading filters nothing yet, so a flaky read never reads as "removed".
  const { knownIndicatorSelections, unknownIndicatorIds } = useMemo(() => {
    if (catalogue.status === "loading") {
      return { knownIndicatorSelections: NO_SELECTIONS, unknownIndicatorIds: [] as string[] };
    }
    if (catalogue.status === "error") {
      return { knownIndicatorSelections: indicatorSelections, unknownIndicatorIds: [] as string[] };
    }
    const known: IndicatorSelection[] = [];
    const unknown: string[] = [];
    for (const selection of indicatorSelections) {
      if (catalogueById.has(selection.id)) known.push(selection);
      else unknown.push(selection.id);
    }
    return { knownIndicatorSelections: known, unknownIndicatorIds: unknown };
  }, [indicatorSelections, catalogue.status, catalogueById]);

  const indicatorsState = useIndicators(
    indicatorSource,
    symbol,
    resolution,
    knownIndicatorSelections,
    barsRange,
  );

  // The colours as they stand now, not as when the archive last answered: picking a swatch has to repaint
  // at once, or choosing one would feel like a read (design.md, "Kolor rozwiązywany przy rysowaniu").
  const instanceColors = useMemo(
    () => new Map(indicatorSelections.map((selection) => [selection.key, selection.color])),
    [indicatorSelections],
  );

  // The same assignment the sync effect makes, kept out of the readout below: `shown` moves on every
  // crosshair pixel and neither `drawnInstances` nor `assignLineColors` needs redoing that often.
  const readoutAssignment = useMemo(() => {
    const drawn = drawnInstances(indicatorsState.selections, indicatorsState.results, catalogueById);
    const colors = colorsRef.current ?? readChartColors();
    return { drawn, lineColors: assignLineColors(drawn, colors, instanceColors) };
  }, [indicatorsState.selections, indicatorsState.results, catalogueById, instanceColors, colorsRef]);

  // The badge has nowhere to put *why*, and the reason is often actionable, so it is raised as a toast keyed
  // per slot. A failed read and an answered read carrying refusals are different states and say so separately.
  const indicatorError = indicatorsState.status === "error" ? indicatorsState.error : null;
  const failedIndicators = indicatorsState.results.filter((result) => result.error !== null);
  // A string, not the array: the array is rebuilt every render and would refire the
  // effect on every one of them.
  const failureDigest = failedIndicators.map((r) => `${r.id}: ${r.error}`).join("\n");

  useEffect(() => {
    if (indicatorError === null && failureDigest === "") return;
    const failedCount = failureDigest === "" ? 0 : failureDigest.split("\n").length;
    showToast({
      key: `indicators:${symbol}:${resolution}`,
      severity: "error",
      title:
        indicatorError !== null
          ? `${symbol} · indicators unavailable`
          : `${symbol} · ${failedCount} of the chosen indicators unavailable`,
      detail: indicatorError ?? failureDigest,
    });
  }, [indicatorError, failureDigest, symbol, resolution]);
  const clearIndicatorWindow = useCallback(() => {
    heldIndicatorWindowRef.current = null;
    setBarsRange(null);
  }, []);

  return {
    indicatorSelections,
    setIndicatorSelections,
    catalogue,
    catalogueById,
    knownIndicatorSelections,
    unknownIndicatorIds,
    indicatorsState,
    instanceColors,
    readoutAssignment,
    failedIndicators,
    failureDigest,
    syncIndicatorWindowRef,
    clearIndicatorWindow,
  };
}
