import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ControllableSource,
  bar,
  createChartStub,
  makeFakeSeries,
  type FakeChart,
} from "./testDoubles";

const stub = createChartStub();

// The real library draws to a canvas jsdom cannot render, let alone assert on.
// Everything below tests what the component *asks the chart to do*.
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: { type: "Candlestick" },
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  createChart: (_container: HTMLElement) => {
    const chart: FakeChart = {
      removed: false,
      resized: [],
      crosshairHandlers: [],
      series: [],
      fitContentCalls: 0,
    };
    stub.charts.push(chart);
    return {
      addSeries: () => {
        const series = makeFakeSeries();
        chart.series.push(series);
        return series;
      },
      remove: () => {
        chart.removed = true;
      },
      resize: (width: number, height: number) => chart.resized.push({ width, height }),
      timeScale: () => ({ fitContent: () => chart.fitContentCalls++ }),
      subscribeCrosshairMove: (h: (p: unknown) => void) => chart.crosshairHandlers.push(h),
      unsubscribeCrosshairMove: (h: (p: unknown) => void) => {
        chart.crosshairHandlers = chart.crosshairHandlers.filter((x) => x !== h);
      },
    };
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
  it("says it is loading before the history lands", () => {
    renderChart(source);
    expect(screen.getByText(/loading us100 history/i)).toBeInTheDocument();
  });

  it("draws the history in one setData once it arrives", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1), bar(200, 2)]);
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
      source.resolveHistory(0, []);
    });
    expect(screen.getByText(/no candles for us100 at minute_5/i)).toBeInTheDocument();
  });

  it("names a failed read and retries it on demand", async () => {
    const user = userEvent.setup();
    renderChart(source);
    await act(async () => {
      source.rejectHistory(0, "unknown instrument 'US100'");
    });

    expect(screen.getByText(/could not load us100/i)).toBeInTheDocument();
    expect(screen.getByText(/unknown instrument 'US100'/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(source.historyCalls).toHaveLength(2);
  });

  it("marks the data stale when the stream drops, instead of showing a frozen candle silently", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1)]);
      source.emit({ kind: "status", state: "reconnecting" });
    });
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
  });
});

describe("Chart — live bars", () => {
  it("updates the last candle in place rather than appending a second one", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1), bar(200, 2, true)]);
      source.emit({ kind: "bar", bar: bar(200, 2.5, true) });
    });

    const series = stub.latest().series[0];
    expect(series.updateCalls.at(-1)).toMatchObject({ time: 200, close: 2.5 });
    expect(series.data()).toHaveLength(2);
  });

  it("appends when a new period opens", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1)]);
      source.emit({ kind: "bar", bar: bar(200, 2, true) });
    });
    expect(stub.latest().series[0].data()).toHaveLength(2);
  });

  it("redraws wholesale when a gap-fill bar arrives older than what is drawn", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1), bar(300, 3)]);
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
      source.resolveHistory(0, [bar(100, 1, true)]);
    });
    expect(screen.getByText(/forming/i)).toBeInTheDocument();

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
      source.resolveHistory(0, [bar(100, 50, false, null)]);
    });
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("keeps a live bar that arrived before the history read finished", async () => {
    renderChart(source);

    // The subscription is live immediately; the history read is still in
    // flight. This ordering is the normal case, not an edge case.
    await act(async () => {
      source.emit({ kind: "bar", bar: bar(300, 3, true) });
    });
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1), bar(200, 2)]);
    });

    const series = stub.latest().series[0];
    expect(series.data().map((c) => c.time)).toEqual([100, 200, 300]);
    expect(screen.getByText(/forming/i)).toBeInTheDocument();
  });

  it("shows a real volume when the source carries one", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1, false, 1234)]);
    });
    expect(screen.getByText("1234")).toBeInTheDocument();
  });
});

describe("Chart — subscription lifecycle", () => {
  it("re-subscribes to the new symbol and drops the old subscription", async () => {
    const { rerender, onResolutionChange } = renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 1)]);
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
      source.resolveHistory(0, [bar(100, 1)]);
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
      source.resolveHistory(0, [bar(100, 1), bar(200, 2)]);
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
    expect(other.historyCalls).toHaveLength(1);
  });

  it("a late response from a superseded resolution never reaches the chart", async () => {
    const { rerender, onResolutionChange } = renderChart(source);

    rerender(
      <Chart source={source} symbol="US100" resolution="HOUR" onResolutionChange={onResolutionChange} />,
    );
    await waitFor(() => {
      expect(source.historyCalls).toHaveLength(2);
    });

    // The HOUR read lands first, then the stale MINUTE_5 one.
    await act(async () => {
      source.resolveHistory(1, [bar(3600, 10)]);
      source.resolveHistory(0, [bar(100, 1), bar(200, 2)]);
    });

    const series = stub.latest().series[0];
    expect(series.data().map((c) => c.time)).toEqual([3600]);
  });
});

describe("Chart — header readout freshness", () => {
  it("follows the forming candle as it moves within one period", async () => {
    renderChart(source);
    await act(async () => {
      source.resolveHistory(0, [bar(100, 50, true)]);
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
