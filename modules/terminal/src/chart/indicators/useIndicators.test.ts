/**
 * `useIndicators` answers with one snapshot: the times, the results, and the selections
 * those results were computed for. `Chart.tsx` binds result to instance by position
 * within that snapshot, so the three must never come from different reads.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { IndicatorSource } from "../../data/source";
import type { IndicatorSelection, IndicatorsResult, Resolution } from "../../data/types";
import { useIndicators } from "./useIndicators";

function selection(key: string, period: number): IndicatorSelection {
  return { key, id: "ema", params: { period }, color: null };
}

function answerFor(specs: IndicatorSelection[]): IndicatorsResult {
  return {
    symbol: "US100",
    resolution: "MINUTE" as Resolution,
    derived: false,
    algorithmVersion: 1,
    times: [1_000],
    results: specs.map((spec) => ({
      id: spec.id,
      params: spec.params,
      warmupBars: 0,
      anchoredAt: null,
      settled: true,
      error: null,
      lines: { ema: [spec.params.period] },
      markers: null,
      zones: null,
      levels: null,
    })),
  };
}

/** A source whose reads are resolved by the test, one at a time. */
function pendingSource() {
  const pending: Array<{ specs: IndicatorSelection[]; resolve(): void }> = [];
  const source: IndicatorSource = {
    computeIndicators(_symbol, _resolution, _from, _to, specs) {
      return new Promise((resolve) => {
        pending.push({ specs: [...specs], resolve: () => resolve(answerFor(specs)) });
      });
    },
    indicatorCatalogue: () => Promise.resolve({ algorithmVersion: 1, indicators: [] }),
  };
  return { source, pending };
}

const RANGE = { from: 0, to: 2_000 };

describe("useIndicators", () => {
  it("carries the selections its results were computed for", async () => {
    const { source, pending } = pendingSource();
    const first = [selection("a", 20)];
    const { result } = renderHook(() =>
      useIndicators(source, "US100", "MINUTE" as Resolution, first, RANGE),
    );

    await act(async () => {
      pending[0].resolve();
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.selections).toEqual(first);
    expect(result.current.results).toHaveLength(1);
  });

  it("does not pair fresh selections with results computed before them", async () => {
    const { source, pending } = pendingSource();
    const first = [selection("a", 20)];
    const second = [selection("a", 20), selection("b", 50)];
    const { result, rerender } = renderHook(
      ({ selections }: { selections: IndicatorSelection[] }) =>
        useIndicators(source, "US100", "MINUTE" as Resolution, selections, RANGE),
      { initialProps: { selections: first } },
    );

    await act(async () => {
      pending[0].resolve();
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // The operator adds an instance while the chart still holds the previous answer.
    rerender({ selections: second });
    expect(result.current.results).toHaveLength(1);
    expect(result.current.selections).toEqual(first);

    await act(async () => {
      pending[1].resolve();
    });
    await waitFor(() => expect(result.current.results).toHaveLength(2));
    expect(result.current.selections).toEqual(second);
  });

  it("keeps the failed read's last good snapshot whole", async () => {
    const { source, pending } = pendingSource();
    const first = [selection("a", 20)];
    const { result, rerender } = renderHook(
      ({ selections }: { selections: IndicatorSelection[] }) =>
        useIndicators(
          selections.length === 2 ? failing : source,
          "US100",
          "MINUTE" as Resolution,
          selections,
          RANGE,
        ),
      { initialProps: { selections: first } },
    );

    await act(async () => {
      pending[0].resolve();
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    rerender({ selections: [selection("a", 20), selection("b", 50)] });

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.results).toHaveLength(1);
    expect(result.current.selections).toEqual(first);
  });
});

const failing: IndicatorSource = {
  computeIndicators: () => Promise.reject(new Error("archive unreachable")),
  indicatorCatalogue: () => Promise.resolve({ algorithmVersion: 1, indicators: [] }),
};
