import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { FakeIndicatorSource, indicatorEntry } from "../chart/testDoubles";
import { SocketHub, type SocketLike } from "../data/socketHub";
import type { Resolution, TrackedPair } from "../data/types";

// Same stub rationale as Chart.test.tsx: the canvas is not assertable.
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: { type: "Candlestick" },
  LineSeries: { type: "Line" },
  HistogramSeries: { type: "Histogram" },
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  LineStyle: { Dashed: 2 },
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, update: () => {} }),
    addPane: () => ({ setStretchFactor: () => {}, paneIndex: () => 1 }),
    removePane: () => {},
    panes: () => [{ setStretchFactor: () => {} }],
    remove: () => {},
    resize: () => {},
    timeScale: () => ({
      fitContent: () => {},
      getVisibleLogicalRange: () => null,
      setVisibleLogicalRange: () => {},
      subscribeVisibleLogicalRangeChange: () => {},
      unsubscribeVisibleLogicalRangeChange: () => {},
    }),
    subscribeCrosshairMove: () => {},
    unsubscribeCrosshairMove: () => {},
  }),
}));

/** What the slot's picker and its resolution restriction both read from — the
 *  list changes per test the way the real archive's would. */
class FakeArchive {
  pairs: TrackedPair[] = [];
  listFailure: Error | null = null;

  listPairs = async () => {
    if (this.listFailure) throw this.listFailure;
    return [...this.pairs];
  };
}

let fakeArchive: FakeArchive;
let fakeIndicators: FakeIndicatorSource | undefined;

// A quiet candle source. The grid's job is layout and slot wiring, not data,
// and a live source would push state updates into these tests at arbitrary
// moments.
vi.mock("../data/marketData", () => ({
  marketData: {
    parts: [],
    searchInstruments: async () => [],
    listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
    history: async () => [],
    // Never sends anything: the charts stay in their loading state, so no
    // async state update lands outside these tests' control.
    subscribe: () => () => {},
  },
  get archive() {
    return fakeArchive;
  },
  // Undefined by default, same as a caller passing no `indicatorSource` at
  // all — the grid's own tests are about layout and slot wiring, not the
  // indicator picker, except the one that is.
  get indicators() {
    return fakeIndicators;
  },
}));

const { GridView } = await import("./GridView");
const { gridStore, STORAGE_KEY } = await import("./gridStore");
const { defaultGridConfig, SLOT_IDS } = await import("./model");

function pair(symbol: string, resolution: Resolution): TrackedPair {
  return {
    symbol,
    resolution,
    addedAt: 0,
    collectFrom: 0,
    earliestCandle: null,
    latestCandle: null,
    collection: "collecting",
    candleCount: 0,
    estimatedBytes: 0,
  };
}

function renderGrid() {
  return render(
    <MemoryRouter>
      <GridView />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  // gridStore is a module singleton holding state in memory, so clearing
  // storage is not enough — put every slot back to defaults so one test's
  // edits cannot leak into the next.
  const defaults = defaultGridConfig();
  gridStore.setLayout(defaults.layout);
  gridStore.setActiveSlot(defaults.activeSlot);
  for (const id of SLOT_IDS) {
    const slot = defaults.slots[id];
    if (slot.symbol === null) gridStore.clearSlotSymbol(id);
    else gridStore.setSlotSymbol(id, slot.symbol);
    gridStore.setSlotResolution(id, slot.resolution);
  }

  fakeArchive = new FakeArchive();
  // Matches `defaultGridConfig`'s own slots, plus a couple of extra
  // instruments the tests pick from the picker. `US100` carries a second
  // resolution so the resolution-switch test still has one to switch to.
  fakeArchive.pairs = [
    pair("US100", "MINUTE_5"),
    pair("US100", "HOUR_4"),
    pair("GOLD", "MINUTE_5"),
    pair("BTCUSD", "HOUR"),
    pair("EURUSD", "MINUTE_15"),
    pair("SILVER", "MINUTE_5"),
    pair("TSLA", "MINUTE_5"),
  ];

  fakeIndicators = undefined;
});

describe("GridView layout (terminal-grid spec)", () => {
  it("renders exactly as many slots as the layout calls for", async () => {
    renderGrid();
    expect(screen.getAllByTestId(/^slot-/)).toHaveLength(4);

    await userEvent.click(screen.getByRole("button", { name: "3x2" }));
    expect(screen.getAllByTestId(/^slot-/)).toHaveLength(6);

    await userEvent.click(screen.getByRole("button", { name: "1x1" }));
    expect(screen.getAllByTestId(/^slot-/)).toHaveLength(1);
  });

  it("keeps a hidden slot's instrument when shrinking and re-expanding", async () => {
    const user = userEvent.setup();
    renderGrid();

    await user.click(screen.getByRole("button", { name: "3x2" }));
    const slot6 = within(screen.getByTestId("slot-s6"));
    await user.selectOptions(
      await slot6.findByRole("combobox", { name: "Symbol for slot s6" }),
      "SILVER",
    );
    await waitFor(() => expect(gridStore.getSnapshot().slots.s6.symbol).toBe("SILVER"));

    await user.click(screen.getByRole("button", { name: "2x2" }));
    expect(screen.queryByTestId("slot-s6")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "3x2" }));
    expect(within(screen.getByTestId("slot-s6")).getByText("SILVER")).toBeInTheDocument();
  });

  it("invites a choice in an empty slot instead of drawing an empty chart", async () => {
    const user = userEvent.setup();
    renderGrid();
    await user.click(screen.getByRole("button", { name: "3x2" }));

    const slot6 = within(screen.getByTestId("slot-s6"));
    expect(slot6.getByText(/pick an instrument/i)).toBeInTheDocument();
  });

  it("marks the slot the operator is acting on", async () => {
    const user = userEvent.setup();
    renderGrid();

    expect(screen.getByTestId("slot-s1")).toHaveAttribute("data-active", "true");
    await user.click(screen.getByTestId("slot-s3"));
    expect(screen.getByTestId("slot-s3")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("slot-s1")).toHaveAttribute("data-active", "false");
  });

  // The mark used to be an `outline` on the slot, which paints with the slot's own
  // background: a chart's opaque section covered it, so only an empty slot ever showed
  // which one was active.
  it("marks the active slot whether it holds a chart or is empty", async () => {
    const user = userEvent.setup();
    renderGrid();

    expect(gridStore.getSnapshot().slots.s1.symbol).not.toBeNull();
    expect(screen.getByTestId("active-mark-s1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "3x2" }));
    await user.click(screen.getByTestId("slot-s6"));

    expect(within(screen.getByTestId("slot-s6")).getByText(/pick an instrument/i)).toBeInTheDocument();
    expect(screen.getByTestId("active-mark-s6")).toBeInTheDocument();
    expect(screen.queryByTestId("active-mark-s1")).not.toBeInTheDocument();
  });

  it("changes one slot's instrument without disturbing the others", async () => {
    const user = userEvent.setup();
    renderGrid();
    const before = gridStore.getSnapshot().slots.s2.symbol;

    const slot1 = within(screen.getByTestId("slot-s1"));
    await user.selectOptions(
      await slot1.findByRole("combobox", { name: "Symbol for slot s1" }),
      "TSLA",
    );

    await waitFor(() => expect(gridStore.getSnapshot().slots.s1.symbol).toBe("TSLA"));
    expect(gridStore.getSnapshot().slots.s2.symbol).toBe(before);
  });

  it("changes one slot's resolution without disturbing the others", async () => {
    const user = userEvent.setup();
    renderGrid();
    const before = gridStore.getSnapshot().slots.s2.resolution;

    const select = within(screen.getByTestId("slot-s1")).getByLabelText("Resolution");
    await user.selectOptions(select, "HOUR_4");

    await waitFor(() => expect(gridStore.getSnapshot().slots.s1.resolution).toBe("HOUR_4"));
    expect(gridStore.getSnapshot().slots.s2.resolution).toBe(before);
  });

  it("persists layout and slots across a remount", async () => {
    const user = userEvent.setup();
    const { unmount } = renderGrid();
    await user.click(screen.getByRole("button", { name: "3x2" }));
    unmount();

    expect(window.localStorage.getItem(STORAGE_KEY)).toContain("3x2");

    renderGrid();
    expect(screen.getAllByTestId(/^slot-/)).toHaveLength(6);

    // Let the fresh mount's own read of the archive settle before the test
    // ends, so its resolution does not land outside any `act()`.
    await waitFor(() => {
      const select = within(screen.getByTestId("slot-s1")).getByLabelText(
        "Resolution",
      ) as HTMLSelectElement;
      expect(select.options).toHaveLength(2);
    });
  });

  it("restores a slot's chosen indicators across a remount, the same as its instrument", async () => {
    fakeIndicators = new FakeIndicatorSource();
    fakeIndicators.catalogueEntries = [indicatorEntry({ id: "ema" })];
    const user = userEvent.setup();

    const { unmount } = renderGrid();
    const slot1 = within(screen.getByTestId("slot-s1"));
    await user.click(await slot1.findByRole("button", { name: /indicators/i }));
    await user.click(await slot1.findByRole("checkbox", { name: /^ema$/i }));

    await waitFor(() =>
      expect(gridStore.getSnapshot().slots.s1.indicators).toEqual([
        expect.objectContaining({ id: "ema", params: { period: 20 }, color: null }),
      ]),
    );
    unmount();

    renderGrid();
    const remountedSlot1 = within(screen.getByTestId("slot-s1"));
    await user.click(await remountedSlot1.findByRole("button", { name: /indicators/i }));
    expect(await remountedSlot1.findByRole("checkbox", { name: /^ema$/i })).toBeChecked();
  });
});

describe("GridView slot — archived-only symbols (terminal-grid spec)", () => {
  it("limits the resolution selector to what the instrument is archived in", async () => {
    renderGrid();

    // GOLD (slot s2) is archived only at MINUTE_5 in this test's fixture.
    const select = within(screen.getByTestId("slot-s2")).getByLabelText(
      "Resolution",
    ) as HTMLSelectElement;
    await waitFor(() => {
      expect([...select.options].map((o) => o.value)).toEqual(["MINUTE_5"]);
    });
  });

  it("offers every archived symbol and nothing else", async () => {
    renderGrid();

    const picker = await within(screen.getByTestId("slot-s1")).findByRole("combobox", {
      name: "Symbol for slot s1",
    });
    await waitFor(() =>
      expect([...(picker as HTMLSelectElement).options].map((option) => option.value)).toEqual([
        "",
        "BTCUSD",
        "EURUSD",
        "GOLD",
        "SILVER",
        "TSLA",
        "US100",
      ]),
    );

    // Archived at two resolutions, offered once: the picker is about the
    // instrument, and the resolution selector beside it is about the rest.
    expect(
      [...(picker as HTMLSelectElement).options].filter((option) => option.value === "US100"),
    ).toHaveLength(1);
  });

  it("says nothing is archived, and points to Instruments, instead of an empty list", async () => {
    fakeArchive.pairs = [];
    const user = userEvent.setup();
    renderGrid();
    await user.click(screen.getByRole("button", { name: "3x2" }));

    const slot6 = within(screen.getByTestId("slot-s6"));
    expect(await slot6.findByText(/nothing is archived yet/i)).toBeInTheDocument();
    expect(slot6.getByRole("link", { name: "Instruments" })).toHaveAttribute(
      "href",
      "/instruments",
    );
    expect(slot6.queryByRole("combobox", { name: "Symbol for slot s6" })).not.toBeInTheDocument();
  });

  it("keeps a slot's instrument when the archived list can't be read, and lets the picker say so", async () => {
    fakeArchive.listFailure = new Error("archive unreachable");
    renderGrid();

    const slot1 = within(screen.getByTestId("slot-s1"));
    expect(slot1.queryByText(/no longer archived/i)).not.toBeInTheDocument();
    expect(slot1.getByText("US100")).toBeInTheDocument();

    expect(await slot1.findByText(/archive unreachable/i)).toBeInTheDocument();
    expect(slot1.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("recognizes a remembered instrument that stopped being archived, leaving other slots alone", async () => {
    fakeArchive.pairs = fakeArchive.pairs.filter((p) => p.symbol !== "US100");
    renderGrid();

    const slot1 = within(screen.getByTestId("slot-s1"));
    expect(await slot1.findByText(/no longer archived/i)).toBeInTheDocument();
    expect(slot1.getByText("US100")).toBeInTheDocument();

    expect(within(screen.getByTestId("slot-s2")).getByText("GOLD")).toBeInTheDocument();
  });

  // The symbol surviving is not enough. Charting US100 MINUTE_5 while the slot's own
  // selector — narrowed to what is archived — shows HOUR_4 would have each contradict
  // the other.
  it("recognizes a remembered resolution that stopped being archived, and offers the ones left", async () => {
    const user = userEvent.setup();
    // US100 keeps HOUR_4 but loses MINUTE_5, which is what slot s1 remembers.
    fakeArchive.pairs = fakeArchive.pairs.filter(
      (p) => !(p.symbol === "US100" && p.resolution === "MINUTE_5"),
    );
    renderGrid();

    const slot1 = within(screen.getByTestId("slot-s1"));
    expect(await slot1.findByText(/no longer archived at/i)).toBeInTheDocument();
    expect(slot1.getByText("m5")).toBeInTheDocument();
    // No chart for a pair nobody collects.
    expect(slot1.queryByLabelText("Resolution")).not.toBeInTheDocument();

    // The resolution that is still collected is one click away.
    await user.click(slot1.getByRole("button", { name: "h4" }));

    await waitFor(() => expect(gridStore.getSnapshot().slots.s1.resolution).toBe("HOUR_4"));
    expect(within(screen.getByTestId("slot-s1")).getByLabelText("Resolution")).toBeInTheDocument();
  });
});

// 6.7's connection claim is about the hub, not the DOM: two slots on the same
// pair must share one socket, and slots that disappear must let theirs go.
describe("Grid connection sharing (terminal-market-data spec)", () => {
  class FakeSocket implements SocketLike {
    onopen: (() => void) | null = null;
    onclose: ((e: { code: number; reason: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    closed = false;
    close() {
      this.closed = true;
    }
  }

  /** A socket exists one microtask after `subscribe`, not on the next line: the
   *  hub asks the archive for a one-time stream ticket before it dials. */
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("shares one connection between two slots on the same pair, and frees it with the last", async () => {
    const sockets: FakeSocket[] = [];
    const hub = new SocketHub(
      async (symbol, resolution) => `ws://test/ws/candles?symbol=${symbol}&resolution=${resolution}`,
      () => [],
      () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    );

    // Two slots showing US100 MINUTE_5, one showing GOLD MINUTE_5.
    const unsubA = hub.subscribe("US100", "MINUTE_5", () => {});
    const unsubB = hub.subscribe("US100", "MINUTE_5", () => {});
    const unsubC = hub.subscribe("GOLD", "MINUTE_5", () => {});
    await settle();

    expect(sockets).toHaveLength(2);
    expect(hub.activeConnectionCount()).toBe(2);

    // Shrinking the layout drops the GOLD slot and one US100 slot.
    unsubC();
    unsubB();
    expect(hub.activeConnectionCount()).toBe(1);
    expect(sockets[1].closed).toBe(true); // GOLD's socket released
    expect(sockets[0].closed).toBe(false); // US100 still has a subscriber

    unsubA();
    expect(hub.activeConnectionCount()).toBe(0);
    expect(sockets[0].closed).toBe(true);
  });

  it("opens at most one connection per pair for a full 3x2 of distinct pairs", async () => {
    const sockets: FakeSocket[] = [];
    const hub = new SocketHub(
      async (symbol, resolution) => `ws://test/ws/candles?symbol=${symbol}&resolution=${resolution}`,
      () => [],
      () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    );

    const pairs = [
      ["US100", "MINUTE_5"],
      ["US500", "MINUTE_5"],
      ["GOLD", "MINUTE_15"],
      ["BTCUSD", "HOUR"],
      ["EURUSD", "MINUTE"],
      ["OIL_CRUDE", "HOUR_4"],
    ] as const;
    const unsubs = pairs.map(([symbol, resolution]) =>
      hub.subscribe(symbol, resolution, () => {}),
    );
    await settle();

    expect(sockets).toHaveLength(6);
    expect(hub.activeConnectionCount()).toBe(6);

    for (const unsub of unsubs) unsub();
    expect(hub.activeConnectionCount()).toBe(0);
    expect(sockets.every((s) => s.closed)).toBe(true);
  });
});
