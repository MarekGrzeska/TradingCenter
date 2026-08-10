import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ControllableSource,
  bar,
  createChartStub,
  fakeChartApi,
  makeFakeChart,
} from "./testDoubles";

const stub = createChartStub();

// The real library draws to a canvas jsdom cannot render, let alone assert on.
// Everything below tests what the component *asks the chart to do*.
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: { type: "Candlestick" },
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  createChart: (_container: HTMLElement) => {
    const chart = makeFakeChart();
    stub.charts.push(chart);
    return fakeChartApi(chart);
  },
}));

const { Chart } = await import("./Chart");

function renderChart(source: ControllableSource, props?: Partial<{ symbol: string; resolution: "MINUTE_5" | "HOUR" }>) {
  const onResolutionChange = vi.fn();
  const view = render(
    <Chart
      source={source}
      symbol={props?.symbol ?? "US100"}
      resolution={props?.resolution ?? "MINUTE_5"}
      onResolutionChange={onResolutionChange}
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
    expect(screen.getByText(/no candles for us100 at minute_5/i)).toBeInTheDocument();
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

  it("flags a forming candle and drops the flag once it settles", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([], bar(100, 1, true));
    });
    // The snapshot's forming bar reaches the header on the next animation
    // frame, like any other live bar.
    await waitFor(() => expect(screen.getByText(/forming/i)).toBeInTheDocument());

    await act(async () => {
      source.emit({ kind: "bar", bar: bar(100, 1.2, false) });
    });
    // Live bars reach the header on the next animation frame, so the badge
    // clears a frame after the canvas does.
    await waitFor(() => expect(screen.queryByText(/forming/i)).not.toBeInTheDocument());
  });

  it("shows a missing volume as unavailable, never as zero", async () => {
    renderChart(source);
    await act(async () => {
      // Prices well away from 0 so a stray "0" in the readout could only be
      // the volume field.
      source.snapshot([bar(100, 50, false, null)]);
    });
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
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
    expect(screen.getByText(/forming/i)).toBeInTheDocument();
  });

  it("shows a real volume when the source carries one", async () => {
    renderChart(source);
    await act(async () => {
      source.snapshot([bar(100, 1, false, 1234)]);
    });
    expect(screen.getByText("1234")).toBeInTheDocument();
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
    source.historyPages = [[bar(40, 0.5)]];
    await drawAndPan();

    // The window is the span the drawn candles occupy (220 - 100), taken
    // backwards from the oldest of them — never forwards, so the live edge the
    // subscription owns is not asked for a second time.
    expect(source.historyCalls).toEqual([
      { symbol: "US100", resolution: "MINUTE_5", from: -20, to: 100 },
    ]);
    expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([40, 100, 160, 220]);
  });

  it("keeps the operator looking at the same candles after a page lands", async () => {
    source.historyPages = [[bar(-20, 0.4), bar(40, 0.5)]];
    await drawAndPan({ from: -5, to: 30 });

    // Two candles joined the front, so every logical index moved by two; the
    // frame moves with them or the chart jumps under the cursor.
    expect(stub.latest().rangesSet.at(-1)).toEqual({ from: -3, to: 32 });
  });

  it("does not chain a second page off its own frame correction", async () => {
    // Correcting the frame is itself a range change, and the corrected frame is
    // still near the left edge. Left alone it would ask for the next page, and
    // that one for the one after it — the whole archive on a single drag.
    source.historyPages = [[bar(-20, 0.4), bar(40, 0.5)], [bar(-80, 0.3)]];
    await drawAndPan();

    // The corrected frame, reported by the time scale once the page is in and
    // the read is over — the moment the loop would start.
    await act(async () => {
      stub.latest().pan(stub.latest().visibleRange!);
    });

    expect(source.historyCalls).toHaveLength(1);
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
      source.releaseHistory([bar(40, 0.5)]);
    });
    expect(screen.queryByText(/loading older/i)).not.toBeInTheDocument();
  });

  it("walks past empty windows before calling it the start of history", async () => {
    // A weekend, a holiday and a pause in collection all look like this: a
    // range with no candles in it. One of them is not the end of the archive.
    source.historyPages = [[], [], [], []];
    await drawAndPan();

    expect(source.historyCalls).toHaveLength(4);
    // Each window doubles, so the four of them reach back eight times the first.
    expect(source.historyCalls.at(-1)).toEqual({
      symbol: "US100",
      resolution: "MINUTE_5",
      from: -1700,
      to: -740,
    });
    expect(screen.getByText(/start of history/i)).toBeInTheDocument();

    await act(async () => {
      stub.latest().pan({ from: -9, to: 26 });
    });
    expect(source.historyCalls).toHaveLength(4);
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
    source.historyPages = [[bar(40, 0.5)]];
    await user.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() =>
      expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([40, 100, 160, 220]),
    );
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
      source.releaseHistory([bar(40, 0.5)]);
    });

    expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([1000]);
  });

  it("does not throw the frame back to the right when the stream reconnects", async () => {
    source.historyPages = [[bar(40, 0.5)]];
    await drawAndPan();
    const fittedOnce = stub.latest().fitContentCalls;

    await act(async () => {
      source.emit({ kind: "status", state: "reconnecting" });
      source.emit({ kind: "status", state: "connected" });
      source.snapshot([...drawn, bar(280, 4)]);
    });

    expect(stub.latest().fitContentCalls).toBe(fittedOnce);
    expect(stub.latest().series[0].data().map((c) => c.time)).toEqual([40, 100, 160, 220, 280]);
  });
});
