import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FakeSeries } from "./testDoubles";
import {
  ControllableSource,
  FakeIndicatorSource,
  bar,
  createChartStub,
  fakeChartApi,
  fakeCreateSeriesMarkers,
  indicatorEntry,
  indicatorResult,
  makeFakeChart,
} from "./testDoubles";
import type { Bar, ChartFocusRequest, IndicatorSelection, Resolution } from "../data/types";
import { indicatorColorFromToken, readChartColors } from "./theme";
import { Toaster } from "../ui/Toaster";
import { toastStore } from "../ui/toastStore";

const stub = createChartStub();

// The real library draws to a canvas jsdom cannot render, let alone assert on.
// Everything below tests what the component *asks the chart to do*.
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: { type: "Candlestick" },
  LineSeries: { type: "Line" },
  HistogramSeries: { type: "Histogram" },
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  LineStyle: { Dashed: 2 },
  createChart: (_container: HTMLElement) => {
    const chart = makeFakeChart();
    stub.charts.push(chart);
    return fakeChartApi(chart);
  },
  createSeriesMarkers: (series: FakeSeries, markers: unknown[] = []) =>
    fakeCreateSeriesMarkers(series, markers),
}));

const { Chart } = await import("./Chart");
type ChartDrawings = import("./Chart").ChartDrawings;
type AgentChartDrawing = import("../agent/agentApi").AgentChartDrawing;

// The store is a module singleton; a toast left behind would show up in the next test's
// document as if that test had raised it.
afterEach(() => act(() => toastStore.clear()));

function renderChart(
  source: ControllableSource,
  props?: Partial<{
    symbol: string;
    resolution: Resolution;
    indicatorSource: FakeIndicatorSource;
    initialIndicatorSelections: IndicatorSelection[];
    onIndicatorSelectionsChange: (selections: IndicatorSelection[]) => void;
    focusRequest: ChartFocusRequest | null;
    onFocusRequestSettled: () => void;
    onVisibleRangeChange: (range: { from: number; to: number } | null) => void;
    drawings: ChartDrawings;
  }>,
) {
  const onResolutionChange = vi.fn();
  const onFocusRequestSettled = props?.onFocusRequestSettled ?? vi.fn();
  const onVisibleRangeChange = props?.onVisibleRangeChange ?? vi.fn();
  const view = render(
    <Chart
      source={source}
      indicatorSource={props?.indicatorSource}
      symbol={props?.symbol ?? "US100"}
      resolution={props?.resolution ?? "MINUTE_5"}
      onResolutionChange={onResolutionChange}
      initialIndicatorSelections={props?.initialIndicatorSelections}
      onIndicatorSelectionsChange={props?.onIndicatorSelectionsChange}
      focusRequest={props?.focusRequest}
      onFocusRequestSettled={onFocusRequestSettled}
      onVisibleRangeChange={onVisibleRangeChange}
      drawings={props?.drawings}
    />,
  );
  return { ...view, onResolutionChange, onFocusRequestSettled, onVisibleRangeChange };
}

let source: ControllableSource;

beforeEach(() => {
  stub.reset();
  source = new ControllableSource();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Chart — resolution picker (terminal-shell spec)", () => {
  it("shows the terminal's own interval labels, never the wire's names", () => {
    renderChart(source, { resolution: "MINUTE_5" });

    const select = screen.getByLabelText("Resolution") as HTMLSelectElement;
    const labels = [...select.options].map((option) => option.textContent);

    expect(labels).toEqual(["m1", "m5", "m15", "m30", "h1", "h4", "day", "week"]);
    expect(labels).not.toContain("MINUTE_5");
  });
});

describe("Chart — feed states (terminal-chart spec)", () => {
  it("says it is loading before the snapshot lands", () => {
    renderChart(source);
    expect(screen.getByText(/loading us100 history/i)).toBeInTheDocument();
  });

  it("draws the snapshot in one setData once it arrives", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    const series = stub.latest().series[0];
    expect(series.setDataCalls.at(-1)).toEqual([
      { time: 100, open: 1, high: 2, low: 0, close: 1 },
      { time: 200, open: 2, high: 3, low: 1, close: 2 },
    ]);
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });

  it("states an empty series rather than showing a blank pane", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([]);
    });
    expect(screen.getByText(/no candles for us100 at m5/i)).toBeInTheDocument();
  });

  it("names a refused subscription and retries it on demand", async () => {
    const user = userEvent.setup();
    renderChart(source);
    await act(async () => {
      // What the archive closes a subscription with when nobody chose to
      // collect the pair — a reason an operator can act on, not a socket code.
      source.refuse("US100 MINUTE_5 is not being collected");
    });

    expect(screen.getByText(/could not load us100/i)).toBeInTheDocument();
    expect(screen.getByText(/is not being collected/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(source.subscribeCalls).toHaveLength(2);
  });

  // jsdom computes no paint order, so this cannot assert what is on top — it
  // asserts the one property that decides it. Found in a browser: the chart
  // library mounts canvases at z-index 1 and 2 inside a container that opens no
  // stacking context, so at the default level every message below rendered,
  // passed its test, and was painted over by an empty canvas.
  it("puts what it has to say above the chart library's canvases", async () => {
    const { container } = renderChart(source);
    await act(async () => {
      source.refuse("US100 MINUTE_5 is not being archived");
    });

    const veil = container.querySelector(".absolute.inset-0.z-10");
    expect(veil).not.toBeNull();
    expect(veil).toHaveTextContent(/could not load us100/i);
  });

  it("never asks for a history of its own — the subscription brings it", async () => {
    // The seam this change removed. A separate history read is exactly what
    // used to leave a window in which a closing candle could go missing.
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
      source.emit({ kind: "status", state: "reconnecting" });
      source.emit({ kind: "status", state: "connected" });
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    expect(source.historyCalls).toHaveLength(0);
  });

  it("fills the outage from the reconnect's snapshot rather than a gap request", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await act(async () => {
      source.emit({ kind: "status", state: "reconnecting" });
      // Back up: the fresh snapshot carries what closed while nobody was
      // listening, so the series closes its own gap.
      source.emit({ kind: "status", state: "connected" });
      source.snapshot([bar(100, 1), bar(200, 2), bar(300, 3)]);
    });

    expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([100, 200, 300]);
    expect(source.historyCalls).toHaveLength(0);
    expect(screen.queryByText(/reconnecting/i)).not.toBeInTheDocument();
  });

  it("marks the data stale when the stream drops, instead of showing a frozen candle silently", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
      source.emit({ kind: "status", state: "reconnecting" });
    });
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
  });
});

describe("Chart — live bars", () => {
  it("updates the last candle in place rather than appending a second one", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)], bar(200, 2, true));
      source.emit({ kind: "bar", bar: bar(200, 2.5, true) });
    });

    const series = stub.latest().series[0];
    expect(series.updateCalls.at(-1)).toMatchObject({ time: 200, close: 2.5 });
    expect(series.data()).toHaveLength(2);
  });

  it("appends when a new period opens", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
      source.emit({ kind: "bar", bar: bar(200, 2, true) });
    });
    expect(stub.latest().series[0].data()).toHaveLength(2);
  });

  it("redraws wholesale when a bar arrives older than what is drawn", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(300, 3)]);
    });
    const series = stub.latest().series[0];
    const setDataBefore = series.setDataCalls.length;

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(200, 2) });
    });

    // update() would throw going backwards, so the merged series is redrawn.
    expect(series.setDataCalls.length).toBe(setDataBefore + 1);
    expect(series.data().map((c) => c.time)).toEqual([100, 200, 300]);
  });

  it("keeps a bar that arrived before the snapshot did", async () => {
    renderChart(source);

    // Not the normal order — the snapshot is the first message by construction
    // — but the merge must not depend on that, or a chart would blank itself
    // the one time the archive reordered anything.
    await act(async () => {
      source.emit({ kind: "bar", bar: bar(300, 3, true) });
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    const series = stub.latest().series[0];
    expect(series.data().map((c) => c.time)).toEqual([100, 200, 300]);
  });

  it("never shows volume, even when the source carries one", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1, false, 1234)]);
    });
    expect(screen.queryByText("1234")).not.toBeInTheDocument();
    expect(screen.queryByText(/^V\b/)).not.toBeInTheDocument();
  });
});

describe("Chart — subscription lifecycle", () => {
  it("re-subscribes to the new symbol and drops the old subscription", async () => {
    const { rerender, onResolutionChange } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    expect(source.subscribeCalls).toEqual([{ symbol: "US100", resolution: "MINUTE_5" }]);

    rerender(
      <Chart
        source={source}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );

    await waitFor(() => {
      expect(source.subscribeCalls).toHaveLength(2);
    });
    expect(source.subscribeCalls[1]).toEqual({ symbol: "GOLD", resolution: "MINUTE_5" });
    expect(source.unsubscribeCount).toBe(1);
  });

  it("tears down the chart and the subscription on unmount", async () => {
    const { unmount } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    unmount();

    expect(stub.latest().removed).toBe(true);
    expect(source.unsubscribeCount).toBe(1);
  });

  it("clears the previous source's candles when the source changes", async () => {
    // Caught live: switching mock → gateway kept the mock series on screen for
    // the seconds the gateway's deep read took, under a "gateway" label.
    const { rerender, onResolutionChange } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    expect(stub.latest().series[0].data()).toHaveLength(2);

    const other = new ControllableSource();
    rerender(
      <Chart
        source={other}
        symbol="US100"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );

    await waitFor(() => {
      expect(stub.latest().series[0].data()).toHaveLength(0);
    });
    expect(other.subscribeCalls).toHaveLength(1);
  });

  it("a late message from a superseded resolution never reaches the chart", async () => {
    const { rerender, onResolutionChange } = renderChart(source);

    rerender(
      <Chart source={source} symbol="US100" resolution="HOUR" onResolutionChange={onResolutionChange} />,
    );
    await waitFor(() => {
      expect(source.subscribeCalls).toHaveLength(2);
    });

    // The HOUR snapshot lands first, then one from the dropped MINUTE_5
    // subscription — the cleanup has run, so it is dead on arrival.
    await act(async () => {
      source.snapshotTo(1, [bar(3600, 10)]);
      source.snapshotTo(0, [bar(100, 1), bar(200, 2)]);
    });

    const series = stub.latest().series[0];
    expect(series.data().map((c) => c.time)).toEqual([3600]);
  });
});

describe("Chart — header readout freshness", () => {
  it("follows the forming candle as it moves within one period", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([], bar(100, 50, true));
    });
    // `bar(t, c)` puts high at c+1, which is unique in the readout.
    await waitFor(() => expect(screen.getByText("51")).toBeInTheDocument());

    // Same period, price moved. `forming` does not change, so nothing else
    // about the component's state does either — which is exactly how the
    // header used to freeze while the canvas kept moving.
    await act(async () => {
      source.emit({ kind: "bar", bar: bar(100, 60, true) });
    });

    await waitFor(() => expect(screen.getByText("61")).toBeInTheDocument());
  });
});

describe("Chart — older history (terminal-chart spec)", () => {
  /** Three settled candles a minute apart: enough for the pager to measure a
   *  page from, and short enough to compute the expected window by hand. */
  const drawn = [bar(100, 1), bar(160, 2), bar(220, 3)];

  /** `count` candles a minute apart, the newest of them one minute before the
   *  drawn series starts — a page as the archive would answer one. */
  function olderPage(count: number): Bar[] {
    return Array.from({ length: count }, (_, index) => bar(100 - (count - index) * 60, 0.5));
  }

  async function drawAndPan(range = { from: -5, to: 30 }) {
    renderChart(source);
    await act(async () => {
      source.snapshot(drawn);
    });
    await act(async () => {
      stub.latest().pan(range);
    });
  }

  it("asks for a range ending at the oldest drawn candle", async () => {
    source.historyPages = [olderPage(60)];
    await drawAndPan();

    // The window is the span the drawn candles occupy (220 - 100), taken
    // backwards from the oldest of them — never forwards, so the live edge the
    // subscription owns is not asked for a second time.
    expect(source.historyCalls[0]).toEqual({
      symbol: "US100",
      resolution: "MINUTE_5",
      from: -20,
      to: 100,
    });
    expect(stub.latest().series[0].data()).toHaveLength(63);
  });

  it("stops once the viewport has candles to its left again", async () => {
    // One page wide enough to put the margin back is one page: the pager is
    // asking "does the operator have room to keep dragging", not "is there more
    // history in the archive".
    source.historyPages = [olderPage(60), olderPage(60)];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(1);
  });

  it("keeps paging when a page is too small to fill the margin", async () => {
    // The bug this replaced: the chart compared logical indices across a series
    // that had just grown at the front, so after a page or two the comparison
    // could no longer be satisfied and paging stopped for good.
    source.historyPages = [olderPage(2), olderPage(60)];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(2);
    // The second window ends where the first page left the series, not where
    // the drawn candles used to start.
    expect(source.historyCalls[1].to).toBe(-20);
  });

  it("stops when a page brings nothing the series did not already have", async () => {
    // A source answering with candles already drawn would otherwise be asked
    // the same question forever.
    source.historyPages = [[bar(100, 1)], [bar(100, 1)]];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(1);
    expect(screen.getByText(/start of history/i)).toBeInTheDocument();
  });

  it("keeps the operator looking at the same candles after a page lands", async () => {
    source.historyPages = [olderPage(60)];
    await drawAndPan({ from: -5, to: 30 });

    // Sixty candles joined the front, so every logical index moved by sixty;
    // the frame moves with them or the chart jumps under the cursor.
    expect(stub.latest().rangesSet.at(-1)).toEqual({ from: 55, to: 90 });
  });

  it("says it is loading, and does not start a second read while one is in flight", async () => {
    source.holdHistory = true;
    await drawAndPan();

    expect(screen.getByText(/loading older/i)).toBeInTheDocument();

    await act(async () => {
      stub.latest().pan({ from: -8, to: 27 });
    });
    expect(source.historyCalls).toHaveLength(1);

    await act(async () => {
      source.releaseHistory(olderPage(60));
    });
    expect(screen.queryByText(/loading older/i)).not.toBeInTheDocument();
  });

  it("walks past empty windows before calling it the start of history", async () => {
    // A weekend, a holiday and a pause in collection all look like this: a
    // range with no candles in it. None of them is the end of the archive, and
    // four windows — which is what this used to walk — reached back three days,
    // less than a long Easter weekend.
    source.historyPages = [];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(8);
    // Each window doubles, so the eight of them reach back 255 times the first.
    expect(source.historyCalls.at(-1)).toEqual({
      symbol: "US100",
      resolution: "MINUTE_5",
      from: -30500,
      to: -15140,
    });
    expect(screen.getByText(/start of history/i)).toBeInTheDocument();

    await act(async () => {
      stub.latest().pan({ from: -9, to: 26 });
    });
    expect(source.historyCalls).toHaveLength(8);
  });

  it("keeps the drawn candles when a page fails, and retries on demand", async () => {
    const user = userEvent.setup();
    source.historyFailure = new Error("the candle archive is unreachable");
    await drawAndPan();

    expect(screen.getByText(/older history failed/i)).toBeInTheDocument();
    expect(stub.latest().series[0].data()).toHaveLength(3);

    // A failure is not retried by panning — that would be a request loop
    // against an archive that is down.
    await act(async () => {
      stub.latest().pan({ from: -9, to: 26 });
    });
    expect(source.historyCalls).toHaveLength(1);

    source.historyFailure = null;
    source.historyPages = [olderPage(60)];
    await user.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(stub.latest().series[0].data()).toHaveLength(63));
    expect(screen.queryByText(/older history failed/i)).not.toBeInTheDocument();
  });

  it("drops a page that arrives after the symbol changed", async () => {
    source.holdHistory = true;
    const { rerender, onResolutionChange } = renderChart(source);
    await act(async () => {
      source.snapshot(drawn);
    });
    await act(async () => {
      stub.latest().pan({ from: -5, to: 30 });
    });

    rerender(
      <Chart
        source={source}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );
    await waitFor(() => expect(source.subscribeCalls).toHaveLength(2));
    await act(async () => {
      source.snapshotTo(1, [bar(1000, 9)]);
      source.releaseHistory(olderPage(60));
    });

    expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([1000]);
  });

  it("does not throw the frame back to the right when the stream reconnects", async () => {
    source.historyPages = [olderPage(60)];
    await drawAndPan();
    const fittedOnce = stub.latest().fitContentCalls;

    await act(async () => {
      source.emit({ kind: "status", state: "reconnecting" });
      source.emit({ kind: "status", state: "connected" });
      source.snapshot([...drawn, bar(280, 4)]);
    });

    expect(stub.latest().fitContentCalls).toBe(fittedOnce);
    expect(stub.latest().series[0].data().at(-1)?.time).toBe(280);
  });
});

describe("Chart — resolution change keeps the frame (terminal-chart spec, agent-chart-navigation)", () => {
  function series(count: number, periodSeconds: number): Bar[] {
    return Array.from({ length: count }, (_, index) => bar(index * periodSeconds, index + 1));
  }

  it("keeps the same stretch of time, converted to the new interval's own candle count", async () => {
    const { rerender, onResolutionChange } = renderChart(source, { resolution: "MINUTE_5" });
    await act(async () => {
      source.snapshot(series(400, 300)); // 400 five-minute candles
    });
    await act(async () => {
      // 240 candles wide (indices 50..290), 72 000 seconds — nowhere near either edge.
      stub.latest().pan({ from: 50, to: 290 });
    });

    rerender(
      <Chart source={source} symbol="US100" resolution="HOUR" onResolutionChange={onResolutionChange} />,
    );
    await act(async () => {
      source.snapshot(series(100, 3600)); // 100 hourly candles
    });

    // 72 000 seconds at an hour a candle is 20; the old midpoint (51 000s) sits nearest
    // hourly candle 14 (50 400s) — from 4 to 23 is candle 14 centred in a span of 20.
    expect(stub.latest().rangesSet.at(-1)).toEqual({ from: 4, to: 23 });
  });

  it("keeps standing at the live edge, on the new interval's own newest candle", async () => {
    const { rerender, onResolutionChange } = renderChart(source, { resolution: "MINUTE_5" });
    await act(async () => {
      source.snapshot(series(400, 300));
    });
    await act(async () => {
      stub.latest().pan({ from: 350, to: 399 }); // the newest candle is in view
    });

    rerender(
      <Chart source={source} symbol="US100" resolution="HOUR" onResolutionChange={onResolutionChange} />,
    );
    await act(async () => {
      source.snapshot(series(50, 3600));
    });

    // Clamped to the floor (14 700 seconds is under four hourly candles), anchored on
    // the newest of the fifty hourly candles rather than its own span's centre.
    expect(stub.latest().rangesSet.at(-1)).toEqual({ from: 40, to: 49 });
  });

  it("floors an interval mismatch too small to read at, instead of showing one or two candles", async () => {
    const { rerender, onResolutionChange } = renderChart(source, { resolution: "MINUTE" });
    await act(async () => {
      source.snapshot(series(100, 60));
    });
    await act(async () => {
      stub.latest().pan({ from: 40, to: 45 }); // five minutes, nowhere near either edge
    });

    rerender(
      <Chart source={source} symbol="US100" resolution="DAY" onResolutionChange={onResolutionChange} />,
    );
    await act(async () => {
      source.snapshot(series(20, 86_400));
    });

    // Five minutes of DAY candles rounds to zero; floored to ten, centred on the nearest
    // of the twenty daily candles to the old span's midpoint (candle 0, the closest one).
    expect(stub.latest().rangesSet.at(-1)).toEqual({ from: -5, to: 4 });
  });

  it("still fits the whole series on a slot's very first draw — nothing to keep yet", async () => {
    renderChart(source, { resolution: "MINUTE_5" });

    await act(async () => {
      source.snapshot(series(10, 300));
    });

    expect(stub.latest().fitContentCalls).toBeGreaterThan(0);
    expect(stub.latest().rangesSet).toHaveLength(0);
  });

  it("does not touch the frame when the symbol changes instead of the resolution", async () => {
    const { rerender, onResolutionChange } = renderChart(source, { resolution: "MINUTE_5" });
    await act(async () => {
      source.snapshot(series(400, 300));
    });
    await act(async () => {
      stub.latest().pan({ from: 50, to: 290 });
    });

    rerender(
      <Chart source={source} symbol="GOLD" resolution="MINUTE_5" onResolutionChange={onResolutionChange} />,
    );
    await act(async () => {
      source.snapshot(series(10, 300));
    });

    // A different instrument's old window means nothing here — the fresh series is
    // simply fitted, the same as any symbol shown for the first time.
    expect(stub.latest().fitContentCalls).toBeGreaterThan(0);
  });
});

describe("Chart — agent focus (terminal-chart spec, agent-chart-navigation)", () => {
  const drawn = [bar(100, 1), bar(160, 2), bar(220, 3)];

  function olderPage(count: number): Bar[] {
    return Array.from({ length: count }, (_, index) => bar(100 - (count - index) * 60, 0.5));
  }

  it("applies a from/to focus already covered by the drawn series, reading nothing more", async () => {
    const focus: ChartFocusRequest = { from: 100, to: 220, around: null, bars: null, lastBars: null };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(drawn);
    });

    expect(stub.latest().timeRangesSet).toContainEqual({ from: 100, to: 220 });
    expect(source.historyCalls).toHaveLength(0);
    expect(onFocusRequestSettled).toHaveBeenCalledTimes(1);
  });

  it("shows the newest N candles for a last-bars focus, by logical range", async () => {
    // Sixty candles, not three: a series this short would itself sit inside the pager's
    // own left-edge margin (`OLDER_MARGIN_BARS`) the moment the logical range narrows to
    // the newest two, which would fetch more history for a reason that has nothing to do
    // with this test.
    const long = Array.from({ length: 60 }, (_, i) => bar(1000 + i * 60, i + 1));
    const focus: ChartFocusRequest = { from: null, to: null, around: null, bars: null, lastBars: 2 };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(long);
    });

    expect(stub.latest().rangesSet).toContainEqual({ from: 58, to: 59 });
    expect(source.historyCalls).toHaveLength(0);
    expect(onFocusRequestSettled).toHaveBeenCalledTimes(1);
  });

  it("centres an around/bars focus on the nearest drawn candle, by logical range", async () => {
    // A hundred candles, well clear of the pager's own left-edge margin — see the
    // last-bars test above for why a three-candle series would confuse this one.
    const long = Array.from({ length: 100 }, (_, i) => bar(1000 + i * 60, i + 1));
    const focus: ChartFocusRequest = {
      from: null,
      to: null,
      around: 1000 + 70 * 60,
      bars: 2,
      lastBars: null,
    };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(long);
    });

    // `around` lands exactly on candle 70; `bars: 2` must show exactly two candles, not
    // three — a range of {69, 71} would be three (69, 70, 71).
    expect(stub.latest().rangesSet).toContainEqual({ from: 69, to: 70 });
    expect(source.historyCalls).toHaveLength(0);
    expect(onFocusRequestSettled).toHaveBeenCalledTimes(1);
  });

  it("pages older history to reach a from/to focus, then applies it", async () => {
    source.historyPages = [olderPage(60)];
    const focus: ChartFocusRequest = { from: -20, to: 220, around: null, bars: null, lastBars: null };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(drawn);
    });

    // One page reaches back to -3500 — far past -20 — so the pager stops there.
    expect(source.historyCalls).toHaveLength(1);
    expect(stub.latest().timeRangesSet).toContainEqual({ from: -20, to: 220 });
    expect(onFocusRequestSettled).toHaveBeenCalledTimes(1);
  });

  it("asks for the whole window to a distant focus in one read, not a page at a time", async () => {
    // The bug this exists for: the pager walks about a day of calendar per page on
    // MINUTE_5 and stops after twenty of them, so a focus five months back was never
    // reached — the chart landed on wherever the walk had got to and looked like it had
    // moved on purpose. A named moment is asked for once, by name.
    source.historyPages = [olderPage(60)];
    const focus: ChartFocusRequest = {
      from: -1_000_000,
      to: 220,
      around: null,
      bars: null,
      lastBars: null,
    };
    renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(drawn);
    });

    expect(source.historyCalls).toHaveLength(1);
    // The window between the moment asked for and the oldest bar drawn — not a page-sized
    // step back from the drawn edge.
    expect(source.historyCalls[0]).toMatchObject({ from: -1_000_000, to: 100 });
  });

  it("reads back past an around/bars focus by the half of it that sits before the moment", async () => {
    // A centred frame needs candles on both sides. Reading only as far back as `around`
    // puts it on the series' first bar, and the frame the operator asked for comes out
    // shifted half a screen to the right.
    const focus: ChartFocusRequest = {
      from: null,
      to: null,
      around: -50_000,
      bars: 100,
      lastBars: null,
    };
    source.historyPages = [olderPage(60)];
    renderChart(source, { focusRequest: focus, resolution: "MINUTE_5" });

    await act(async () => {
      source.snapshot(drawn);
    });

    // 50 candles of MINUTE_5 before the moment named: 50 * 300 seconds.
    expect(source.historyCalls[0]).toMatchObject({ from: -50_000 - 15_000, to: 100 });
  });

  it("settles a focus the archive has no candles far enough back for", async () => {
    // One read is the whole attempt, so the wait ends either way. Before `stoppedShort`
    // the request sat in `pendingFocusRef` unsettled: the chart never moved,
    // `onFocusRequestSettled` never fired, and the grid store went on offering the same
    // request until the symbol changed.
    source.historyPages = [olderPage(60)]; // reaches -3500, nowhere near the target
    const focus: ChartFocusRequest = {
      from: -1_000_000,
      to: 220,
      around: null,
      bars: null,
      lastBars: null,
    };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });

    await act(async () => {
      source.snapshot(drawn);
    });

    await waitFor(() => expect(onFocusRequestSettled).toHaveBeenCalledTimes(1));
    // Applied against what was actually reached, not abandoned: the fragment is partly
    // there, which is the case `overlapsSeries` exists for.
    expect(stub.latest().timeRangesSet).toContainEqual({ from: -1_000_000, to: 220 });
  });

  it("skips a focus the archive has nothing for, leaves the view alone, and says so", async () => {
    source.historyPages = []; // every read answers empty
    const focus: ChartFocusRequest = {
      from: -1_000_000,
      to: -999_000,
      around: null,
      bars: null,
      lastBars: null,
    };
    const { onFocusRequestSettled } = renderChart(source, { focusRequest: focus });
    render(<Toaster />);

    await act(async () => {
      source.snapshot(drawn);
    });

    expect(stub.latest().timeRangesSet).toHaveLength(0);
    expect(onFocusRequestSettled).toHaveBeenCalledTimes(1);
    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("US100");
    expect(toast).toHaveTextContent(/outside the archive/i);
  });

  it("does not pursue a focus that was never given", async () => {
    renderChart(source, { focusRequest: null });

    await act(async () => {
      source.snapshot(drawn);
    });

    expect(stub.latest().timeRangesSet).toHaveLength(0);
    expect(source.historyCalls).toHaveLength(0);
  });

  it("lets the operator pan freely after a focus applies, without snapping back", async () => {
    // `pan()` is what a drag looks like from the library's side: it moves the range and
    // notifies subscribers, the same as `setVisibleLogicalRange` — but it is not a call
    // `Chart.tsx` itself made, so it never lands in `rangesSet`, which only records what
    // this component wrote. A focus that kept re-asserting itself would show up there as
    // a second write; one that behaved would not.
    const focus: ChartFocusRequest = { from: null, to: null, around: null, bars: null, lastBars: 2 };
    renderChart(source, { focusRequest: focus });
    await act(async () => {
      source.snapshot(drawn);
    });
    const rangesWrittenByTheFocus = stub.latest().rangesSet.length;

    await act(async () => {
      stub.latest().pan({ from: 0, to: 2 });
    });

    expect(stub.latest().rangesSet.length).toBe(rangesWrittenByTheFocus);
    expect(stub.latest().visibleRange).toEqual({ from: 0, to: 2 });
  });
});

describe("Chart — reports the visible range (terminal-agent-chat spec, agent-chart-navigation)", () => {
  it("reports the drawn bars' own times at the visible logical range, on a pan", async () => {
    const { onVisibleRangeChange } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(160, 2), bar(220, 3), bar(280, 4)]);
    });

    await act(async () => {
      stub.latest().pan({ from: 1, to: 2 });
    });

    expect(onVisibleRangeChange).toHaveBeenLastCalledWith({ from: 160, to: 220 });
  });

  it("reports null while nothing is drawn yet", async () => {
    const { onVisibleRangeChange } = renderChart(source);

    await act(async () => {
      stub.latest().pan({ from: 0, to: 1 });
    });

    expect(onVisibleRangeChange).toHaveBeenLastCalledWith(null);
  });

  it("reports null once the chart is torn down", async () => {
    const { unmount, onVisibleRangeChange } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(160, 2), bar(220, 3)]);
    });
    await act(async () => {
      stub.latest().pan({ from: 0, to: 2 });
    });

    unmount();

    expect(onVisibleRangeChange).toHaveBeenLastCalledWith(null);
  });
});

describe("Chart — the price on the right-hand scale", () => {
  it("leaves the library's own last-value label off", async () => {
    // It is sourced from the last *visible* bar, so panning into history had it
    // announce the price of whatever candle sat at the edge of the viewport.
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    expect(stub.latest().series[0].options).toMatchObject({
      lastValueVisible: false,
      priceLineVisible: false,
    });
  });

  it("marks the newest close, and follows it as the candle forms", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 50), bar(160, 60)]);
    });
    await waitFor(() => expect(stub.latest().series[0].priceLine()?.options.price).toBe(60));

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(220, 70, true) });
    });
    await waitFor(() => expect(stub.latest().series[0].priceLine()?.options.price).toBe(70));
  });

  it("stays on the newest close when the operator pans back into history", async () => {
    source.historyPages = [];
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 50), bar(160, 60), bar(220, 70)]);
    });
    await act(async () => {
      stub.latest().pan({ from: -5, to: 30 });
    });

    expect(stub.latest().series[0].priceLine()?.options.price).toBe(70);
  });

  it("takes its mark down when the chart is emptied for a new symbol", async () => {
    const { rerender, onResolutionChange } = renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 50)]);
    });
    const line = stub.latest().series[0].priceLine();
    expect(line).toBeDefined();

    rerender(
      <Chart
        source={source}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );

    await waitFor(() => expect(line?.removed).toBe(true));
  });
});

describe("Chart — indicators (terminal-chart spec, market-data-indicators)", () => {
  function lineSeries() {
    return stub.latest().series.filter((s) => s.type === "Line");
  }

  it("offers no picker at all without an indicator source", () => {
    renderChart(source);
    expect(screen.queryByRole("button", { name: /indicators/i })).not.toBeInTheDocument();
  });

  it("builds the picker from the catalogue, not from a hand-kept list", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry({ id: "ema", name: "Exponential Moving Average" })];
    renderChart(source, { indicatorSource: indicators });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));

    expect(await screen.findByText("EMA")).toBeInTheDocument();
  });

  it("computes the chosen indicator over the range the chart actually drew, and draws a line", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [indicatorResult({ lines: { ema: [10, 20] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    expect(indicators.computeCalls[0]).toMatchObject({
      symbol: "US100",
      resolution: "MINUTE_5",
      from: 100,
      to: 200,
      specs: [expect.objectContaining({ id: "ema", params: { period: 20 }, color: null })],
    });

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    expect(lineSeries()[0].data()).toEqual([
      { time: 100, value: 10 },
      { time: 200, value: 20 },
    ]);
  });

  it("restores a saved selection on mount, computes it without a click, and notifies every later change", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    const onIndicatorSelectionsChange = vi.fn();
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "ema", id: "ema", params: { period: 20 }, color: null }],
      onIndicatorSelectionsChange,
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    expect(indicators.computeCalls[0]).toMatchObject({ specs: [{ id: "ema" }] });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    expect(await screen.findByRole("checkbox", { name: /^ema$/i })).toBeChecked();

    // Toggling it off is a real change — the caller (the grid slot) hears
    // about it so it can save the new, now-empty selection.
    await userEvent.click(screen.getByRole("checkbox", { name: /^ema$/i }));
    expect(onIndicatorSelectionsChange).toHaveBeenCalledWith([]);
  });

  it("keeps showing the newest known indicator value once the pointer leaves the chart, even when the freshest bar has none yet", async () => {
    // Indicators are computed over `redraw`'s own range, not on every live tick — so the
    // bar the readout falls back to without a crosshair (the newest one) is routinely a
    // beat ahead of what the archive has answered for. The line itself still ends at the
    // last value it has; the readout must say the same thing, not go blank.
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "ema", id: "ema", params: { period: 20 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));

    // No crosshair move: `shown` falls back to the bar at time 200, which the indicator
    // has no computed value for.
    expect(await screen.findByText("EMA 20")).toBeInTheDocument();
    expect(await screen.findByText("10.00")).toBeInTheDocument();
  });

  it("draws an indicator the slot gained from outside the picker, without remounting", async () => {
    // What `syncAgentChart` (`chartControl.ts`) does after the agent sets the chart:
    // it writes straight to `gridStore`, which hands this component a *new*
    // `initialIndicatorSelections` array on its next render — the same component
    // instance, never remounted. Before the sync effect below existed, the lazy
    // `useState` initializer had already run once at mount and never looked at the
    // prop again, so the operator saw nothing until they reloaded the page.
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    const { rerender } = renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    expect(lineSeries()).toHaveLength(0);

    rerender(
      <Chart
        source={source}
        indicatorSource={indicators}
        symbol="US100"
        resolution="MINUTE_5"
        onResolutionChange={() => {}}
        initialIndicatorSelections={[{ key: "ema", id: "ema", params: { period: 20 }, color: null }]}
      />,
    );

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
  });

  it("skips a saved selection the catalogue no longer offers, and says so, without discarding it from the next save", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry({ id: "ema" })];
    const onIndicatorSelectionsChange = vi.fn();
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "retired_indicator", id: "retired_indicator", params: {}, color: null },
        { key: "ema", id: "ema", params: { period: 20 }, color: null },
      ],
      onIndicatorSelectionsChange,
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    // Only the indicator the catalogue still recognizes is ever asked for.
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    expect(indicators.computeCalls[0].specs).toEqual([{ key: "ema", id: "ema", params: { period: 20 }, color: null }]);

    expect(await screen.findByText(/1 saved indicator unavailable/i)).toBeInTheDocument();

    // An unrelated edit (toggling EMA off) must not silently drop the entry
    // the catalogue does not recognize — nothing here decided it is gone for
    // good, only that it cannot be drawn right now.
    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));
    expect(onIndicatorSelectionsChange).toHaveBeenLastCalledWith([
      { key: "retired_indicator", id: "retired_indicator", params: {}, color: null },
    ]);
  });

  it("draws an own-pane indicator in a pane of its own, not the price pane", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "atr",
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: "atr", label: "ATR {period}", style: null }],
        render: { pane: "own", style: "line", scale: "own", autoscale: true, range: null, levels: [] },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ id: "atr", params: { period: 14 }, lines: { atr: [1.5, 1.6] } }),
        ],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr$/i }));

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    // Pane 0 is the price pane the candles live on — an own-pane indicator must
    // land anywhere else, in a pane `Chart` created for it.
    expect(lineSeries()[0].paneIndex).not.toBe(0);
    expect(stub.latest().panesList).toHaveLength(2);

    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(0));
    expect(stub.latest().panesList).toHaveLength(1);
  });

  it("deselecting one of two own-pane indicators leaves the other's pane intact (regression)", async () => {
    // Reported: select atr_pct, select atr, deselect atr — the chart's own
    // default is to remove a pane the instant its last series does, which
    // raced `Chart.tsx`'s own explicit `removePane` and threw ("This view
    // hit an error"). Fixed by `addPane(true)` (`preserveEmptyPane`) plus a
    // guard that never hands `removePane` a pane already gone.
    const indicators = new FakeIndicatorSource();
    const ownPaneLine = (id: string) =>
      indicatorEntry({
        id,
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: id, label: id, style: null }],
        render: { pane: "own", style: "line", scale: "own", autoscale: true, range: null, levels: [] },
      });
    indicators.catalogueEntries = [ownPaneLine("atr_pct"), ownPaneLine("atr")];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ id: "atr_pct", params: { period: 14 }, lines: { atr_pct: [1] } })],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({ id: "atr_pct", params: { period: 14 }, lines: { atr_pct: [1] } }),
          indicatorResult({ id: "atr", params: { period: 14 }, lines: { atr: [2] } }),
        ],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ id: "atr_pct", params: { period: 14 }, lines: { atr_pct: [1] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr_pct$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(1));

    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(2));
    expect(stub.latest().panesList).toHaveLength(3); // price + atr_pct + atr

    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr$/i }));

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    expect(lineSeries()[0].options.color).toBeDefined(); // still a live, readable series
    expect(stub.latest().panesList).toHaveLength(2); // price + atr_pct — atr's pane is gone, only once
  });

  it("draws the catalogue's reference levels (RSI's 30/70) once, and removes them when deselected", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "rsi",
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: "rsi", label: "RSI {period}", style: null }],
        render: {
          pane: "own",
          style: "line",
          scale: "fixed",
          autoscale: false,
          range: [0, 100],
          levels: [30, 70],
        },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ id: "rsi", params: { period: 14 }, lines: { rsi: [40, 60] } }),
        ],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^rsi$/i }));

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    const rsiLine = lineSeries()[0];
    const levelPrices = rsiLine.priceLines.filter((l) => !l.removed).map((l) => l.options.price);
    expect(levelPrices).toEqual([30, 70]);

    await userEvent.click(await screen.findByRole("checkbox", { name: /^rsi$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(0));
    // Explicitly removed, not just orphaned along with the series it sat on.
    expect(rsiLine.priceLines.every((l) => l.removed)).toBe(true);
  });

  it("shows an own-pane indicator's value under the cursor beside OHLC, same as a price-pane one", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "rsi",
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: "rsi", label: "RSI {period}", style: null }],
        render: {
          pane: "own",
          style: "line",
          scale: "fixed",
          autoscale: false,
          range: [0, 100],
          levels: [30, 70],
        },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ id: "rsi", params: { period: 14 }, lines: { rsi: [40, 63.5] } }),
        ],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^rsi$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(1));

    await act(async () => {
      for (const handler of stub.latest().crosshairHandlers) handler({ time: 200 });
    });

    expect(await screen.findByText("RSI 14")).toBeInTheDocument();
    expect(await screen.findByText("63.50")).toBeInTheDocument();
  });

  it("draws MACD's histogram line as a two-color Histogram series beside its two Line series", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "macd",
        params: [
          { name: "fast_period", type: "int", default: 12, min: 2, max: 5000 },
          { name: "slow_period", type: "int", default: 26, min: 2, max: 5000 },
          { name: "signal_period", type: "int", default: 9, min: 2, max: 5000 },
        ],
        lines: [
          { key: "macd", label: "MACD {fast_period},{slow_period}", style: null },
          { key: "signal", label: "Signal {signal_period}", style: null },
          { key: "histogram", label: "Histogram", style: "histogram" },
        ],
        render: { pane: "own", style: "line", scale: "own", autoscale: true, range: null, levels: [] },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200, 300],
        results: [
          indicatorResult({
            id: "macd",
            params: { fast_period: 12, slow_period: 26, signal_period: 9 },
            lines: {
              macd: [1, 2, 3],
              signal: [0.5, 0.5, 0.5],
              histogram: [0.5, -1.5, 2.5],
            },
          }),
        ],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2), bar(300, 3)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^macd$/i }));

    await waitFor(() =>
      expect(stub.latest().series.filter((s) => s.type === "Histogram")).toHaveLength(1),
    );
    expect(lineSeries()).toHaveLength(2); // macd, signal — the histogram line is not among them

    const histogram = stub.latest().series.find((s) => s.type === "Histogram")!;
    const colors = readChartColors();
    expect(histogram.data()).toEqual([
      { time: 100, value: 0.5, color: colors.up },
      { time: 200, value: -1.5, color: colors.down },
      { time: 300, value: 2.5, color: colors.up },
    ]);
  });

  it("draws a missing value as a whitespace point, never as zero", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [indicatorResult({ lines: { ema: [null, 20] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));

    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    const [first] = lineSeries()[0].data();
    expect(first).toEqual({ time: 100 });
    expect(first).not.toHaveProperty("value");
  });

  it("says when a value is not settled yet, without hiding it", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ settled: false, lines: { ema: [10] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));

    expect(await screen.findByText(/warming up/i)).toBeInTheDocument();
    await waitFor(() => expect(lineSeries()).toHaveLength(1));
  });

  it("a failed compute leaves the candles alone and offers a retry", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeFailure = new Error("the archive refused: unknown indicator");
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));

    expect(await screen.findByText(/indicators unavailable/i)).toBeInTheDocument();
    // The candlestick series is untouched — still whatever the snapshot drew.
    expect(stub.latest().series[0].data()).toHaveLength(2);

    const callsBefore = indicators.computeCalls.length;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(indicators.computeCalls.length).toBeGreaterThan(callsBefore));
  });

  // `indicator-result-names-its-own-failure`: the archive answers, and one of the chosen
  // indicators carries a reason where its values would have been.
  describe("one indicator carries a reason, the rest carry answers", () => {
    function partialCompute() {
      return {
        symbol: "US100",
        resolution: "MINUTE_5" as const,
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ id: "ema", lines: { ema: [10, 20] } }),
          indicatorResult({
            id: "range_gap",
            settled: false,
            error: "no MINUTE_5 series collected for 'US100'",
            lines: null,
          }),
        ],
      };
    }

    async function pickBoth(indicators: FakeIndicatorSource) {
      await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
      await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));
      await userEvent.click(await screen.findByRole("checkbox", { name: /^range_gap$/i }));
      return indicators;
    }

    function twoEntries() {
      const indicators = new FakeIndicatorSource();
      indicators.catalogueEntries = [
        indicatorEntry(),
        indicatorEntry({ id: "range_gap", name: "Range Gap", output: "zones", group: "zones" }),
      ];
      return indicators;
    }

    it("draws the ones that computed and names the one that did not", async () => {
      const indicators = twoEntries();
      indicators.computeQueue = [partialCompute(), partialCompute()];
      renderChart(source, { indicatorSource: indicators });
      await act(async () => {
        source.snapshot([bar(100, 1), bar(200, 2)]);
      });
      await pickBoth(indicators);

      await waitFor(() => expect(lineSeries()).toHaveLength(1));
      // Named by id: with several chosen, a count sends the operator looking for which.
      expect(await screen.findByText(/range_gap unavailable/i)).toBeInTheDocument();
    });

    it("leaves no empty primitive behind for the one that could not be computed", async () => {
      const indicators = twoEntries();
      indicators.computeQueue = [partialCompute(), partialCompute()];
      renderChart(source, { indicatorSource: indicators });
      await act(async () => {
        source.snapshot([bar(100, 1), bar(200, 2)]);
      });
      await pickBoth(indicators);

      await waitFor(() => expect(lineSeries()).toHaveLength(1));
      // An empty zone primitive would be the terminal drawing "computed, found none"
      // over a result that says the opposite.
      expect(stub.latest().series[0].primitives).toHaveLength(0);
    });

    it("keeps it selected — the operator chose it and the archive may yet hold the series", async () => {
      const indicators = twoEntries();
      indicators.computeQueue = [partialCompute(), partialCompute(), partialCompute()];
      const onIndicatorSelectionsChange = vi.fn();
      renderChart(source, { indicatorSource: indicators, onIndicatorSelectionsChange });
      await act(async () => {
        source.snapshot([bar(100, 1), bar(200, 2)]);
      });
      await pickBoth(indicators);

      await waitFor(() => expect(lineSeries()).toHaveLength(1));
      expect(screen.getByRole("checkbox", { name: /^range_gap$/i })).toBeChecked();
      // What the grid slot saves is what was last reported, and it still has both.
      const saved = onIndicatorSelectionsChange.mock.lastCall?.[0] ?? [];
      expect(saved.map((s: { id: string }) => s.id).sort()).toEqual(["ema", "range_gap"]);
    });

    it("draws it on the next read that succeeds, without being picked again", async () => {
      const indicators = twoEntries();
      const computed = {
        ...partialCompute(),
        results: [
          indicatorResult({ id: "ema", lines: { ema: [10, 20] } }),
          indicatorResult({
            id: "range_gap",
            lines: null,
            zones: [
              {
                from: 100,
                to: 200,
                top: 12,
                bottom: 10,
                direction: "bullish",
                touchedAt: null,
                filledAt: null,
              },
            ],
          }),
        ],
      };
      indicators.computeQueue = [partialCompute(), partialCompute(), computed, computed];
      renderChart(source, { indicatorSource: indicators });
      await act(async () => {
        source.snapshot([bar(100, 1), bar(200, 2)]);
      });
      await pickBoth(indicators);
      await waitFor(() => expect(screen.queryByText(/range_gap unavailable/i)).toBeInTheDocument());

      // A new candle closes, the chart requeries with the same request shape, and this
      // time the archive has what it needed.
      await act(async () => {
        source.emit({ kind: "bar", bar: bar(300, 3, true) }); // 200 just closed
      });

      await waitFor(() =>
        expect(screen.queryByText(/range_gap unavailable/i)).not.toBeInTheDocument(),
      );
      expect(stub.latest().series[0].primitives.length).toBeGreaterThan(0);
    });
  });

  it("raises the reason as a toast, where the badge has nowhere to put it", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeFailure = new Error(
      "no MINUTE_5 series collected for 'US100', and none could be derived from MINUTE either",
    );
    renderChart(source, { indicatorSource: indicators });
    // Mounted the way `Shell` mounts it: once, beside the view, not inside it.
    render(<Toaster />);
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));

    // The badge says *that*; the toast is the only place that says *why*, and the why is
    // the actionable half — a series nobody collected is a thing the operator can go fix.
    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("US100");
    expect(toast).toHaveTextContent(/no MINUTE_5 series collected/);
  });

  it("removes the line when the operator deselects the indicator", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    const checkbox = await screen.findByRole("checkbox", { name: /^ema$/i });
    await userEvent.click(checkbox);
    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    const line = lineSeries()[0];

    await userEvent.click(checkbox);

    await waitFor(() => expect(lineSeries()).toHaveLength(0));
    expect(stub.latest().removedSeries).toContain(line);
  });

  it("clears every indicator line when the symbol changes, before the new series loads", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    const { rerender, onResolutionChange } = renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(1));

    rerender(
      <Chart
        source={source}
        indicatorSource={indicators}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );

    await waitFor(() => expect(lineSeries()).toHaveLength(0));
  });

  it("refuses a parameter outside the range the catalogue declares, and says what range does apply", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
    ];
    renderChart(source, { indicatorSource: indicators });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));

    const periodInput = screen.getByLabelText("period");
    await userEvent.clear(periodInput);
    await userEvent.type(periodInput, "99999");
    await userEvent.tab(); // blur

    expect(await screen.findByText(/must be between 2 and 5000/i)).toBeInTheDocument();
    // The out-of-range value never reached a request — still the one call from selecting it.
    expect(indicators.computeCalls).toHaveLength(1);
  });

  it("keeps an own-pane markers/levels/zones indicator unselectable — no primitive draws one off the price pane", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "own_pane_zones",
        name: "Own-Pane Zones (hypothetical)",
        output: "zones",
        render: { pane: "own", style: "line", scale: "price", autoscale: true, range: null, levels: [] },
      }),
    ];
    renderChart(source, { indicatorSource: indicators });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));

    expect(await screen.findByRole("checkbox", { name: /^own_pane_zones$/i })).toBeDisabled();
  });

  it("makes a price-pane zones indicator (range_gap, session ranges, …) selectable — E3's primitive draws it", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({ id: "range_gap", name: "Range Gap", output: "zones" }),
    ];
    renderChart(source, { indicatorSource: indicators });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));

    expect(await screen.findByRole("checkbox", { name: /^range_gap$/i })).not.toBeDisabled();
  });

  it("makes an own-pane indicator (RSI, ATR, …) selectable and drawable, not just price-pane overlays", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "atr",
        name: "Average True Range",
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: "atr", label: "ATR {period}", style: null }],
        render: { pane: "own", style: "line", scale: "own", autoscale: true, range: null, levels: [] },
      }),
    ];
    renderChart(source, { indicatorSource: indicators });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));

    expect(await screen.findByRole("checkbox", { name: /^atr$/i })).not.toBeDisabled();
  });
});

describe("Chart — indicators markers (terminal-chart spec, task 3.8)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  const swingPointsEntry = indicatorEntry({
    id: "swing_points",
    name: "Swing Points",
    output: "markers",
    params: [{ name: "n", type: "int", default: 2, min: 1, max: 50 }],
    lines: [],
    render: { pane: "price", style: "dots", scale: "price", autoscale: true, range: null, levels: [] },
  });

  it("draws a markers-output indicator through createSeriesMarkers on the price series", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [swingPointsEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({
            id: "swing_points",
            params: { n: 2 },
            lines: null,
            markers: [{ time: 100, label: "Swing High", price: 105 }],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "swing_points", id: "swing_points", params: { n: 2 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    await waitFor(() => expect(priceSeries().markerPlugins).toHaveLength(1));

    const [plugin] = priceSeries().markerPlugins;
    expect(plugin.markers).toEqual([
      expect.objectContaining({ time: 100, price: 105, text: "Swing High" }),
    ]);
    expect(plugin.detached).toBe(false);
  });

  it("stops drawing the markers once the indicator is deselected", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [swingPointsEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "swing_points",
            params: { n: 2 },
            lines: null,
            markers: [{ time: 100, label: "Swing High", price: 105 }],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "swing_points", id: "swing_points", params: { n: 2 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().markerPlugins).toHaveLength(1));
    const [plugin] = priceSeries().markerPlugins;

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^swing_points$/i }));

    await waitFor(() => expect(plugin.detached).toBe(true));
  });
});

describe("Chart — indicators levels / ray primitive (terminal-chart spec, task 3.9)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  const htfLevelsEntry = indicatorEntry({
    id: "htf_levels_day",
    name: "Previous Day Levels",
    output: "levels",
    params: [],
    lines: [],
    render: { pane: "price", style: "line", scale: "price", autoscale: true, range: null, levels: [] },
  });

  it("attaches one ray primitive per (indicator, params), not one per level", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [htfLevelsEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "htf_levels_day",
            params: {},
            lines: null,
            levels: [
              { from: 100, price: 110, label: "PD High", count: null },
              { from: 100, price: 95, label: "PD Low", count: null },
            ],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "htf_levels_day", id: "htf_levels_day", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));
  });

  it("updates the same primitive's levels on recompute instead of attaching a new one", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [htfLevelsEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "htf_levels_day",
            params: {},
            lines: null,
            levels: [{ from: 100, price: 110, label: "PD High", count: null }],
          }),
        ],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({
            id: "htf_levels_day",
            params: {},
            lines: null,
            levels: [{ from: 200, price: 130, label: "PD High", count: null }],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "htf_levels_day", id: "htf_levels_day", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(2));

    // Still exactly one primitive on the series — the second recompute updated
    // it in place rather than attaching a second one alongside the first.
    expect(priceSeries().primitives).toHaveLength(1);
  });

  it("detaches the ray primitive once the indicator is deselected", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [htfLevelsEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "htf_levels_day",
            params: {},
            lines: null,
            levels: [{ from: 100, price: 110, label: "PD High", count: null }],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "htf_levels_day", id: "htf_levels_day", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^htf_levels_day$/i }));

    await waitFor(() => expect(priceSeries().primitives).toHaveLength(0));
  });
});

describe("Chart — indicators zones / zone primitive (terminal-chart spec, task 4.7)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  const rangeGapEntry = indicatorEntry({
    id: "range_gap",
    name: "Range Gap",
    output: "zones",
    params: [{ name: "skip_session_gaps", type: "int", default: 1, min: 0, max: 1 }],
    lines: [],
    render: { pane: "price", style: "line", scale: "price", autoscale: true, range: null, levels: [] },
  });

  it("attaches one zone primitive per (indicator, params), not one per zone", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [rangeGapEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "range_gap",
            params: { skip_session_gaps: 1 },
            lines: null,
            zones: [
              { from: 100, to: null, top: 21, bottom: 20, direction: "bullish", touchedAt: null, filledAt: null },
              { from: 200, to: 300, top: 15, bottom: 10, direction: "bearish", touchedAt: 250, filledAt: 300 },
            ],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "range_gap", id: "range_gap", params: { skip_session_gaps: 1 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));
  });

  it("updates the same primitive's zones on recompute instead of attaching a new one", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [rangeGapEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "range_gap",
            params: { skip_session_gaps: 1 },
            lines: null,
            zones: [
              { from: 100, to: null, top: 21, bottom: 20, direction: "bullish", touchedAt: null, filledAt: null },
            ],
          }),
        ],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({
            id: "range_gap",
            params: { skip_session_gaps: 1 },
            lines: null,
            zones: [
              { from: 100, to: 200, top: 21, bottom: 20, direction: "bullish", touchedAt: 200, filledAt: 200 },
            ],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "range_gap", id: "range_gap", params: { skip_session_gaps: 1 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(2));

    expect(priceSeries().primitives).toHaveLength(1);
  });

  it("detaches the zone primitive once the indicator is deselected", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [rangeGapEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "range_gap",
            params: { skip_session_gaps: 1 },
            lines: null,
            zones: [
              { from: 100, to: null, top: 21, bottom: 20, direction: "bullish", touchedAt: null, filledAt: null },
            ],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "range_gap", id: "range_gap", params: { skip_session_gaps: 1 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^range_gap$/i }));

    await waitFor(() => expect(priceSeries().primitives).toHaveLength(0));
  });
});

describe("Chart — indicators time profile / histogram primitive (terminal-chart spec, task 5.4)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  const timeProfileEntry = indicatorEntry({
    id: "time_profile",
    name: "Time Profile",
    output: "levels",
    params: [],
    lines: [],
    // `render.style: "histogram"` on a `levels` entry is what routes this to
    // `TimeProfilePrimitive` instead of `RayPrimitive` — see `canDrawIndicator`.
    render: { pane: "price", style: "histogram", scale: "price", autoscale: true, range: null, levels: [] },
  });

  it("routes a histogram-style levels entry to the profile primitive, not the ray primitive", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [timeProfileEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "time_profile",
            params: {},
            lines: null,
            levels: [
              { from: 100, price: 20, label: "POC", count: 8 },
              { from: 100, price: 21, label: null, count: 3 },
              { from: 100, price: 22, label: "VAH", count: null },
              { from: 100, price: 19, label: "VAL", count: null },
            ],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "time_profile", id: "time_profile", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));
  });

  it("detaches the profile primitive once the indicator is deselected", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [timeProfileEntry];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "time_profile",
            params: {},
            lines: null,
            levels: [{ from: 100, price: 20, label: "POC", count: 8 }],
          }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "time_profile", id: "time_profile", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^time_profile$/i }));

    await waitFor(() => expect(priceSeries().primitives).toHaveLength(0));
  });
});

describe("Chart — several instances of one indicator, each with its own colour", () => {
  function lineSeries() {
    return stub.latest().series.filter((s) => s.type === "Line");
  }

  /** Two EMAs on one chart, answered in the order they were asked for. */
  function twoEmas(indicators: FakeIndicatorSource) {
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ params: { period: 20 }, lines: { ema: [10, 20] } }),
          indicatorResult({ params: { period: 50 }, lines: { ema: [11, 21] } }),
        ],
      },
    ];
  }

  it("draws the same entry twice, each instance with its own values", async () => {
    const indicators = new FakeIndicatorSource();
    twoEmas(indicators);
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: null },
        { key: "slow", id: "ema", params: { period: 50 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await waitFor(() => expect(lineSeries()).toHaveLength(2));
    expect(lineSeries()[0].data()).toEqual([
      { time: 100, value: 10 },
      { time: 200, value: 20 },
    ]);
    expect(lineSeries()[1].data()).toEqual([
      { time: 100, value: 11 },
      { time: 200, value: 21 },
    ]);
  });

  it("paints an instance in the colour the operator chose, and leaves the other to the cycle", async () => {
    const indicators = new FakeIndicatorSource();
    twoEmas(indicators);
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: "--color-indicator-5" },
        { key: "slow", id: "ema", params: { period: 50 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await waitFor(() => expect(lineSeries()).toHaveLength(2));
    const colors = readChartColors();
    const chosen = indicatorColorFromToken(colors, "--color-indicator-5");
    expect(lineSeries()[0].options.color).toBe(chosen);
    // The cycle steps over a hue already spoken for, so the neighbouring line cannot
    // come out the same colour by accident.
    expect(lineSeries()[1].options.color).not.toBe(chosen);
    expect(colors.indicatorLines).toContain(lineSeries()[1].options.color);
  });

  it("picking a colour for one instance never repaints another still on Auto", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({ params: { period: 10 }, lines: { ema: [1] } }),
          indicatorResult({ params: { period: 20 }, lines: { ema: [2] } }),
          indicatorResult({ params: { period: 50 }, lines: { ema: [3] } }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "one", id: "ema", params: { period: 10 }, color: null },
        { key: "two", id: "ema", params: { period: 20 }, color: null },
        { key: "three", id: "ema", params: { period: 50 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(lineSeries()).toHaveLength(3));
    const [firstBefore, secondBefore] = lineSeries().map((s) => s.options.color);

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    // The third instance, still on Auto, is given a colour by hand — `theme.ts`'s own
    // invariant on `indicatorLines` ("indexed by how many indicator lines are already
    // drawn — never by which one a line is") says the first two must not move.
    const thirdInstance = within(await screen.findByRole("group", { name: "EMA 3" }));
    await userEvent.click(thirdInstance.getByRole("button", { name: "Colour 1" }));

    await waitFor(() => expect(lineSeries()).toHaveLength(3));
    expect(lineSeries()[0].options.color).toBe(firstBefore);
    expect(lineSeries()[1].options.color).toBe(secondBefore);
    const chosen = indicatorColorFromToken(readChartColors(), "--color-accent");
    expect(lineSeries()[2].options.color).toBe(chosen);
  });

  it("draws two instances of one entry in two colours the operator picked", async () => {
    const indicators = new FakeIndicatorSource();
    twoEmas(indicators);
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: "--color-indicator-2" },
        { key: "slow", id: "ema", params: { period: 50 }, color: "--color-indicator-7" },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    await waitFor(() => expect(lineSeries()).toHaveLength(2));
    const colors = readChartColors();
    expect(lineSeries()[0].options.color).toBe(indicatorColorFromToken(colors, "--color-indicator-2"));
    expect(lineSeries()[1].options.color).toBe(indicatorColorFromToken(colors, "--color-indicator-7"));
  });

  it("keeps a chosen colour when another instance is added afterwards", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ params: { period: 20 }, lines: { ema: [10] } })],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({ params: { period: 20 }, lines: { ema: [10] } }),
          indicatorResult({ params: { period: 20 }, lines: { ema: [10] } }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: "--color-indicator-5" },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    const chosen = indicatorColorFromToken(readChartColors(), "--color-indicator-5");
    expect(lineSeries()[0].options.color).toBe(chosen);

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add another ema/i }));

    await waitFor(() => expect(lineSeries()).toHaveLength(2));
    expect(lineSeries()[0].options.color).toBe(chosen);
  });

  it("repaints a line the moment its colour is picked, without asking the archive again", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ params: { period: 20 }, lines: { ema: [10] } })],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(lineSeries()).toHaveLength(1));
    const readsBefore = indicators.computeCalls.length;

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Colour 5" }));

    const chosen = indicatorColorFromToken(readChartColors(), "--color-indicator-5");
    await waitFor(() => expect(lineSeries()[0].options.color).toBe(chosen));
    expect(indicators.computeCalls).toHaveLength(readsBefore);
  });

  it("clears a restored colour back to the cycle when the operator picks Auto", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ params: { period: 20 }, lines: { ema: [10] } })],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: "--color-indicator-5" },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    const chosen = indicatorColorFromToken(readChartColors(), "--color-indicator-5");
    await waitFor(() => expect(lineSeries()[0]?.options.color).toBe(chosen));

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Auto" }));

    // Picking Auto is a choice too, and it must land without waiting for a recompute.
    await waitFor(() => expect(lineSeries()[0].options.color).not.toBe(chosen));
    expect(indicators.computeCalls).toHaveLength(1);
  });

  it("gives the crosshair readout one entry per instance, each labelled with its own params", async () => {
    const indicators = new FakeIndicatorSource();
    twoEmas(indicators);
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: null },
        { key: "slow", id: "ema", params: { period: 50 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    await waitFor(() => expect(lineSeries()).toHaveLength(2));

    await act(async () => {
      for (const handler of stub.latest().crosshairHandlers) handler({ time: 200 });
    });

    expect(await screen.findByText("EMA 20")).toBeInTheDocument();
    expect(await screen.findByText("EMA 50")).toBeInTheDocument();
    expect(await screen.findByText("20.00")).toBeInTheDocument();
    expect(await screen.findByText("21.00")).toBeInTheDocument();
  });

  it("draws the readout over the chart rather than in the header, so its height cannot resize the chart", async () => {
    // The bug this locks: in the header, the readout's height was part of the layout, so
    // a value changing width mid-pan re-wrapped its row, changed the chart container's
    // height, and set the `ResizeObserver` re-laying out the whole chart in the middle of
    // a drag. An overlay cannot change what the chart is given — and must not swallow the
    // drag either, hence `pointer-events-none`.
    const indicators = new FakeIndicatorSource();
    twoEmas(indicators);
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "fast", id: "ema", params: { period: 20 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });

    const readout = await screen.findByTestId("chart-readout");
    expect(readout.className).toContain("pointer-events-none");
    expect(document.querySelector("header")?.contains(readout)).toBe(false);
  });

  it("puts several instances of one indicator on one readout row, and a different indicator on its own", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry(),
      indicatorEntry({
        id: "rsi",
        params: [{ name: "period", type: "int", default: 14, min: 2, max: 5000 }],
        lines: [{ key: "rsi", label: "RSI {period}", style: null }],
        render: { pane: "own", style: "line", scale: "fixed", autoscale: false, range: [0, 100], levels: [] },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [
          indicatorResult({ id: "ema", params: { period: 20 }, lines: { ema: [10, 20] } }),
          indicatorResult({ id: "ema", params: { period: 50 }, lines: { ema: [11, 21] } }),
          indicatorResult({ id: "rsi", params: { period: 14 }, lines: { rsi: [40, 63.5] } }),
        ],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { key: "fast", id: "ema", params: { period: 20 }, color: null },
        { key: "slow", id: "ema", params: { period: 50 }, color: null },
        { key: "strength", id: "rsi", params: { period: 14 }, color: null },
      ],
    });
    await act(async () => {
      source.snapshot([bar(100, 1), bar(200, 2)]);
    });
    await waitFor(() => expect(lineSeries()).toHaveLength(3));

    await act(async () => {
      for (const handler of stub.latest().crosshairHandlers) handler({ time: 200 });
    });

    const rows = await screen.findAllByTestId("indicator-readout-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("EMA 20")).toBeInTheDocument();
    expect(within(rows[0]).getByText("EMA 50")).toBeInTheDocument();
    expect(within(rows[1]).getByText("RSI 14")).toBeInTheDocument();
  });
});

describe("Chart — live indicators (terminal-chart spec, task 6.1/6.2/6.4)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  it("requeries once a candle closes — same request shape, `to` slid to the bar that just settled", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [indicatorResult({ lines: { ema: [10, 11] } })],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "ema", id: "ema", params: { period: 20 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    expect(indicators.computeCalls[0]).toMatchObject({ from: 100, to: 100 });

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(200, 2, true) }); // 100 just closed, 200 now forming
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(2));
    // Same window as before — `applyBar` slides `to` to the bar that closed
    // (100), not to the new forming one (200), which `useIndicators` never sees.
    expect(indicators.computeCalls[1]).toMatchObject({ from: 100, to: 100 });
  });

  it("never requeries while the same candle keeps forming, even right after a close (task 6.2)", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [indicatorResult({ lines: { ema: [10] } })],
      },
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100, 200],
        results: [indicatorResult({ lines: { ema: [10, 11] } })],
      },
    ];
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "ema", id: "ema", params: { period: 20 }, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(200, 2, true) }); // closes 100, opens 200 forming
    });
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(2));

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(200, 2.5, true) }); // 200 still forming, just ticked
      source.emit({ kind: "bar", bar: bar(200, 2.8, true) });
    });
    await act(async () => {}); // let any wrongly-triggered requery's microtasks land

    expect(indicators.computeCalls).toHaveLength(2); // unchanged from the one close above
  });

  it("clears a non-lines primitive (a zone) on a symbol change too, not just indicator lines (task 6.3/6.4)", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({
        id: "range_gap",
        name: "Range Gap",
        output: "zones",
        params: [],
        lines: [],
        render: { pane: "price", style: "line", scale: "price", autoscale: true, range: null, levels: [] },
      }),
    ];
    indicators.computeQueue = [
      {
        symbol: "US100",
        resolution: "MINUTE_5",
        derived: false,
        algorithmVersion: 1,
        times: [100],
        results: [
          indicatorResult({
            id: "range_gap",
            params: {},
            lines: null,
            zones: [
              { from: 100, to: null, top: 21, bottom: 20, direction: "bullish", touchedAt: null, filledAt: null },
            ],
          }),
        ],
      },
    ];
    const { rerender, onResolutionChange } = renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [{ key: "range_gap", id: "range_gap", params: {}, color: null }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));

    rerender(
      <Chart
        source={source}
        indicatorSource={indicators}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
      />,
    );

    // `barsRange` going null the instant the symbol changes empties
    // `indicatorsState.results` before the new series has even loaded — the
    // previous symbol's zone primitive must not linger through that gap.
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(0));
  });
});

describe("Chart — objects drawn on the instrument (terminal-chart spec, agent-chart-drawings)", () => {
  function priceSeries() {
    return stub.latest().series.find((s) => s.type === "Candlestick")!;
  }

  function drawing(id: number, geometry: AgentChartDrawing["geometry"]): AgentChartDrawing {
    return {
      id,
      symbol: "US100",
      geometry,
      label: null,
      color: null,
      createdAt: 1767398400,
      updatedAt: 1767398400,
    };
  }

  function chartDrawings(items: AgentChartDrawing[]): ChartDrawings {
    return {
      items,
      status: "ready",
      error: null,
      remove: async () => null,
      patch: async () => null,
    };
  }

  const THREE_SHAPES = [
    drawing(1, { kind: "level", price: 110, at: null }),
    drawing(2, { kind: "zone", top: 120, bottom: 115, from: null, to: null }),
    drawing(3, {
      kind: "trendline",
      a: { time: 100, price: 90 },
      b: { time: 200, price: 130 },
    }),
  ];

  it("attaches one primitive per drawing, for all three shapes", async () => {
    renderChart(source, { drawings: chartDrawings(THREE_SHAPES) });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(priceSeries().primitives).toHaveLength(3));
  });

  it("keeps the objects through a resolution change", async () => {
    // The one thing that separates a drawing from an indicator: it belongs to the
    // instrument, not to the view, so the interval changing must not take it off
    // (`terminal-chart` spec, "Zmiana rozdzielczości MUST zachować narysowane obiekty").
    const items = chartDrawings(THREE_SHAPES);
    const { rerender, onResolutionChange } = renderChart(source, { drawings: items });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(3));
    const attached = [...priceSeries().primitives];

    rerender(
      <Chart
        source={source}
        symbol="US100"
        resolution="HOUR"
        onResolutionChange={onResolutionChange}
        drawings={items}
      />,
    );
    await act(async () => {
      source.snapshot([bar(200, 1)]);
    });

    // The same instances, not merely the same count: rebuilding them would be a redraw
    // the operator sees as a flicker, and a new instance is how a shared map with the
    // indicators would have shown up.
    expect(priceSeries().primitives).toEqual(attached);
  });

  it("replaces them when the symbol changes", async () => {
    const { rerender, onResolutionChange } = renderChart(source, {
      drawings: chartDrawings(THREE_SHAPES),
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(3));

    rerender(
      <Chart
        source={source}
        symbol="GOLD"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
        drawings={chartDrawings([drawing(9, { kind: "level", price: 2400, at: null })])}
      />,
    );

    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));
  });

  it("takes a removed object off without touching the others", async () => {
    const { rerender, onResolutionChange } = renderChart(source, {
      drawings: chartDrawings(THREE_SHAPES),
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(3));
    const kept = priceSeries().primitives[0];

    rerender(
      <Chart
        source={source}
        symbol="US100"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
        drawings={chartDrawings([THREE_SHAPES[0]])}
      />,
    );

    await waitFor(() => expect(priceSeries().primitives).toEqual([kept]));
  });

  it("draws nothing and offers no list when the caller passes none", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    expect(priceSeries().primitives).toHaveLength(0);
    expect(screen.queryByLabelText("Drawn objects")).toBeNull();
  });
});
