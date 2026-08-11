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
  indicatorEntry,
  indicatorResult,
  makeFakeChart,
} from "./testDoubles";
import type { Bar, IndicatorSelection } from "../data/types";
import { readChartColors } from "./theme";

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

function renderChart(
  source: ControllableSource,
  props?: Partial<{
    symbol: string;
    resolution: "MINUTE_5" | "HOUR";
    indicatorSource: FakeIndicatorSource;
    initialIndicatorSelections: IndicatorSelection[];
    onIndicatorSelectionsChange: (selections: IndicatorSelection[]) => void;
  }>,
) {
  const onResolutionChange = vi.fn();
  const view = render(
    <Chart
      source={source}
      indicatorSource={props?.indicatorSource}
      symbol={props?.symbol ?? "US100"}
      resolution={props?.resolution ?? "MINUTE_5"}
      onResolutionChange={onResolutionChange}
      initialIndicatorSelections={props?.initialIndicatorSelections}
      onIndicatorSelectionsChange={props?.onIndicatorSelectionsChange}
    />,
  );
  return { ...view, onResolutionChange };
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

describe("Chart — wskaźniki (terminal-chart spec, market-data-indicators)", () => {
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

  it("computes the chosen wskaźnik over the range the chart actually drew, and draws a line", async () => {
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
      specs: [{ id: "ema", params: { period: 20 } }],
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
      initialIndicatorSelections: [{ id: "ema", params: { period: 20 } }],
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

  it("skips a saved selection the catalogue no longer offers, and says so, without discarding it from the next save", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [indicatorEntry({ id: "ema" })];
    const onIndicatorSelectionsChange = vi.fn();
    renderChart(source, {
      indicatorSource: indicators,
      initialIndicatorSelections: [
        { id: "retired_indicator", params: {} },
        { id: "ema", params: { period: 20 } },
      ],
      onIndicatorSelectionsChange,
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    // Only the wskaźnik the catalogue still recognizes is ever asked for.
    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    expect(indicators.computeCalls[0].specs).toEqual([{ id: "ema", params: { period: 20 } }]);

    expect(await screen.findByText(/1 saved indicator unavailable/i)).toBeInTheDocument();

    // An unrelated edit (toggling EMA off) must not silently drop the entry
    // the catalogue does not recognize — nothing here decided it is gone for
    // good, only that it cannot be drawn right now.
    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /^ema$/i }));
    expect(onIndicatorSelectionsChange).toHaveBeenLastCalledWith([
      { id: "retired_indicator", params: {} },
    ]);
  });

  it("draws an own-pane wskaźnik in a pane of its own, not the price pane", async () => {
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
    // Pane 0 is the price pane the candles live on — an own-pane wskaźnik must
    // land anywhere else, in a pane `Chart` created for it.
    expect(lineSeries()[0].paneIndex).not.toBe(0);
    expect(stub.latest().panesList).toHaveLength(2);

    await userEvent.click(await screen.findByRole("checkbox", { name: /^atr$/i }));
    await waitFor(() => expect(lineSeries()).toHaveLength(0));
    expect(stub.latest().panesList).toHaveLength(1);
  });

  it("deselecting one of two own-pane wskaźniki leaves the other's pane intact (regression)", async () => {
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

  it("shows an own-pane wskaźnik's value under the cursor beside OHLC, same as a price-pane one", async () => {
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
    expect(await screen.findByText("63.5")).toBeInTheDocument();
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

  it("removes the line when the operator deselects the wskaźnik", async () => {
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

  it("clears every wskaźnik line when the symbol changes, before the new series loads", async () => {
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

  it("keeps an own-pane markers/levels/zones wskaźnik unselectable — no primitive draws one off the price pane", async () => {
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

  it("makes a price-pane zones wskaźnik (range_gap, session ranges, …) selectable — E3's primitive draws it", async () => {
    const indicators = new FakeIndicatorSource();
    indicators.catalogueEntries = [
      indicatorEntry({ id: "range_gap", name: "Range Gap", output: "zones" }),
    ];
    renderChart(source, { indicatorSource: indicators });

    await userEvent.click(await screen.findByRole("button", { name: /indicators/i }));

    expect(await screen.findByRole("checkbox", { name: /^range_gap$/i })).not.toBeDisabled();
  });

  it("makes an own-pane wskaźnik (RSI, ATR, …) selectable and drawable, not just price-pane overlays", async () => {
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

describe("Chart — wskaźniki markers (terminal-chart spec, task 3.8)", () => {
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

  it("draws a markers-output wskaźnik through createSeriesMarkers on the price series", async () => {
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
      initialIndicatorSelections: [{ id: "swing_points", params: { n: 2 } }],
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

  it("stops drawing the markers once the wskaźnik is deselected", async () => {
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
      initialIndicatorSelections: [{ id: "swing_points", params: { n: 2 } }],
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

describe("Chart — wskaźniki levels / ray primitive (terminal-chart spec, task 3.9)", () => {
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

  it("attaches one ray primitive per (wskaźnik, params), not one per level", async () => {
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
      initialIndicatorSelections: [{ id: "htf_levels_day", params: {} }],
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
      initialIndicatorSelections: [{ id: "htf_levels_day", params: {} }],
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

  it("detaches the ray primitive once the wskaźnik is deselected", async () => {
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
      initialIndicatorSelections: [{ id: "htf_levels_day", params: {} }],
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

describe("Chart — wskaźniki zones / zone primitive (terminal-chart spec, task 4.7)", () => {
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

  it("attaches one zone primitive per (wskaźnik, params), not one per zone", async () => {
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
      initialIndicatorSelections: [{ id: "range_gap", params: { skip_session_gaps: 1 } }],
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
      initialIndicatorSelections: [{ id: "range_gap", params: { skip_session_gaps: 1 } }],
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

  it("detaches the zone primitive once the wskaźnik is deselected", async () => {
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
      initialIndicatorSelections: [{ id: "range_gap", params: { skip_session_gaps: 1 } }],
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

describe("Chart — wskaźniki time profile / histogram primitive (terminal-chart spec, task 5.4)", () => {
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
      initialIndicatorSelections: [{ id: "time_profile", params: {} }],
    });
    await act(async () => {
      source.snapshot([bar(100, 1)]);
    });

    await waitFor(() => expect(indicators.computeCalls).toHaveLength(1));
    await waitFor(() => expect(priceSeries().primitives).toHaveLength(1));
  });

  it("detaches the profile primitive once the wskaźnik is deselected", async () => {
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
      initialIndicatorSelections: [{ id: "time_profile", params: {} }],
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

describe("Chart — wskaźniki na żywo (terminal-chart spec, task 6.1/6.2/6.4)", () => {
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
      initialIndicatorSelections: [{ id: "ema", params: { period: 20 } }],
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
      initialIndicatorSelections: [{ id: "ema", params: { period: 20 } }],
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

  it("clears a non-lines primitive (a zone) on a symbol change too, not just wskaźnik lines (task 6.3/6.4)", async () => {
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
      initialIndicatorSelections: [{ id: "range_gap", params: {} }],
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
