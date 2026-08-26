import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FakeSeries } from "./testDoubles";
import {
  ControllableSource,
  FakeIndicatorSource,
  bar,
  createChartStub,
  fakeChartApi,
  fakeCreateSeriesMarkers,
  indicatorAnswer,
  indicatorEntry,
  indicatorResult,
  makeFakeChart,
} from "./testDoubles";
import type { Bar, ChartFocusRequest, IndicatorSelection, Resolution } from "../data/types";
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

  // jsdom computes no paint order, so this asserts the one property that decides it. Found in a browser:
  // the library mounts canvases inside a container that opens no stacking context.
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

    // Not the normal order — the snapshot is the first message by construction — but the merge must not
    // depend on that, or a chart would blank itself the one time the archive reordered anything.
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

    // Same period, price moved. `forming` does not change, so nothing else about the component's state
    // does either — which is exactly how the header used to freeze while the canvas kept moving.
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

    // The window is the span the drawn candles occupy, taken backwards from the oldest of them — never
    // forwards, so the live edge the subscription owns is not asked for a second time.
    expect(source.historyCalls[0]).toEqual({
      symbol: "US100",
      resolution: "MINUTE_5",
      from: -20,
      to: 100,
    });
    expect(stub.latest().series[0].data()).toHaveLength(63);
  });

  it("stops once the viewport has candles to its left again", async () => {
    // One page wide enough to put the margin back is one page: the pager asks "does the operator have
    // room to keep dragging", not "is there more history in the archive".
    source.historyPages = [olderPage(60), olderPage(60)];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(1);
  });

  it("keeps paging when a page is too small to fill the margin", async () => {
    // The bug this replaced: the chart compared logical indices across a series that had just grown at
    // the front, so after a page or two the comparison could not be satisfied and paging stopped.
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
    // A weekend, a holiday and a pause in collection all look like this: a range with no candles in it.
    // Four windows — which is what this used to walk — reached back less than a long Easter weekend.
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
    // Sixty candles, not three: a series this short would sit inside the pager's own left-edge margin the
    // moment the range narrows, fetching history for a reason unrelated to this test.
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
    // The bug this exists for: the pager walks about a day of calendar per page and stops after twenty, so
    // a focus five months back was never reached. A named moment is asked for once, by name.
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
    // A centred frame needs candles on both sides. Reading only as far back as `around` puts it on the
    // series' first bar, and the frame comes out shifted half a screen to the right.
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

  it("applies a focus that arrives in the same breath as a resolution change", async () => {
    // One `set_chart` carrying both is one commit here. Reported from a live session — the interval
    // changed and the chart stayed where it was, and only a second, focus-only request moved it.
    const { rerender, onResolutionChange, onFocusRequestSettled } = renderChart(source, {
      resolution: "MINUTE_5",
    });
    await act(async () => {
      source.snapshot(drawn);
    });

    const focus: ChartFocusRequest = { from: 100, to: 220, around: null, bars: null, lastBars: null };
    rerender(
      <Chart
        source={source}
        symbol="US100"
        resolution="HOUR"
        onResolutionChange={onResolutionChange}
        focusRequest={focus}
        onFocusRequestSettled={onFocusRequestSettled}
      />,
    );
    // The new interval's own series, which is what the focus has to be applied against.
    await act(async () => {
      source.snapshot(drawn);
    });

    await waitFor(() => expect(onFocusRequestSettled).toHaveBeenCalledTimes(1));
    expect(stub.latest().timeRangesSet).toContainEqual({ from: 100, to: 220 });
  });

  it("applies a distant focus that arrives with a resolution change, not only the change", async () => {
    // The shape the live session actually sent: one `set_chart` with a symbol, an interval, indicators
    // and a focus months back.
    source.historyPages = [olderPage(60), olderPage(60)];
    const { rerender, onResolutionChange, onFocusRequestSettled } = renderChart(source, {
      resolution: "HOUR",
    });
    await act(async () => {
      source.snapshot(drawn);
    });

    const focus: ChartFocusRequest = {
      from: -2_000,
      to: -1_000,
      around: null,
      bars: null,
      lastBars: null,
    };
    rerender(
      <Chart
        source={source}
        symbol="US100"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
        focusRequest={focus}
        onFocusRequestSettled={onFocusRequestSettled}
      />,
    );
    await act(async () => {
      source.snapshot(drawn);
    });

    await waitFor(() => expect(onFocusRequestSettled).toHaveBeenCalledTimes(1));
    expect(stub.latest().timeRangesSet).toContainEqual({ from: -2_000, to: -1_000 });
  });

  it("does not lose a new focus to the abandoning of the one before it", async () => {
    // The live sequence: a focus that could not be reached sat pending, and the next command carried a
    // new focus *and* a new interval. The interval change abandons whatever was pending.
    source.historyPages = []; // nothing older, so the first focus stays out of reach
    const first: ChartFocusRequest = {
      from: -9_000_000,
      to: -8_999_000,
      around: null,
      bars: null,
      lastBars: null,
    };
    const { rerender, onResolutionChange, onFocusRequestSettled } = renderChart(source, {
      resolution: "HOUR",
      focusRequest: first,
    });
    await act(async () => {
      source.snapshot(drawn);
    });

    const second: ChartFocusRequest = { from: 100, to: 220, around: null, bars: null, lastBars: null };
    rerender(
      <Chart
        source={source}
        symbol="US100"
        resolution="MINUTE_5"
        onResolutionChange={onResolutionChange}
        focusRequest={second}
        onFocusRequestSettled={onFocusRequestSettled}
      />,
    );
    await act(async () => {
      source.snapshot(drawn);
    });

    await waitFor(() => expect(stub.latest().timeRangesSet).toContainEqual({ from: 100, to: 220 }));
  });

  it("settles a focus the archive has no candles far enough back for", async () => {
    // One read is the whole attempt, so the wait ends either way. Before `stoppedShort` the request sat
    // unsettled: the chart never moved and the store went on offering the same request.
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
    // `pan()` is what a drag looks like from the library's side, and it is not a call `Chart.tsx` made —
    // so a focus that kept re-asserting itself would show up in `rangesSet`, and one that behaved would not.
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

  /** The default EMA entry, answering one compute with `values` at `times`. */
  function emaSource(times: number[], values: number[]): FakeIndicatorSource {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry()];
    indicators.computeQueue = [
      indicatorAnswer(times, [indicatorResult({ lines: { ema: values } })]),
    ];
    return indicators;
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
    const indicators = emaSource([100, 200], [10, 20]);
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
    const indicators = emaSource([100], [10]);
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

  it("removes the line when the operator deselects the indicator", async () => {
    const indicators = emaSource([100], [10]);
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
    const indicators = emaSource([100], [10]);
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
});
