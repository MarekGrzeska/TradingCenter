import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { SocketHub, type SocketLike } from "../data/socketHub";
import type { Resolution, TrackedPair } from "../data/types";

// Same stub rationale as Chart.test.tsx: the canvas is not assertable.
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: { type: "Candlestick" },
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, update: () => {} }),
    remove: () => {},
    resize: () => {},
    timeScale: () => ({ fitContent: () => {} }),
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
}));

const { GridView } = await import("./GridView");
const { gridStore, STORAGE_KEY } = await import("./gridStore");
const { defaultGridConfig, SLOT_IDS } = await import("./model");

function pair(symbol: string, resolution: Resolution): TrackedPair {
  return { symbol, resolution, addedAt: 0, collectFrom: 0, latestCandle: null, collection: "collecting" };
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
    await user.click(slot6.getByRole("combobox", { name: "Symbol for slot s6" }));
    await user.click(await screen.findByRole("option", { name: /^SILVER/ }));
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

  it("changes one slot's instrument without disturbing the others", async () => {
    const user = userEvent.setup();
    renderGrid();
    const before = gridStore.getSnapshot().slots.s2.symbol;

    const slot1 = within(screen.getByTestId("slot-s1"));
    await user.click(slot1.getByRole("button", { name: "Clear Symbol for slot s1" }));
    await user.click(slot1.getByRole("combobox", { name: "Symbol for slot s1" }));
    await user.click(await screen.findByRole("option", { name: /^TSLA/ }));

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

  it("says nothing archived matches, and points to Instruments, when the picker is empty", async () => {
    fakeArchive.pairs = [];
    const user = userEvent.setup();
    renderGrid();
    await user.click(screen.getByRole("button", { name: "3x2" }));

    await user.click(
      within(screen.getByTestId("slot-s6")).getByRole("combobox", {
        name: "Symbol for slot s6",
      }),
    );

    expect(await screen.findByText(/add instruments in the instruments tab/i)).toBeInTheDocument();
  });

  it("keeps a slot's instrument when the archived list can't be read, and lets the picker say so", async () => {
    fakeArchive.listFailure = new Error("archive unreachable");
    const user = userEvent.setup();
    renderGrid();

    const slot1 = within(screen.getByTestId("slot-s1"));
    expect(slot1.queryByText(/no longer archived/i)).not.toBeInTheDocument();
    expect(slot1.getByText("US100")).toBeInTheDocument();

    await user.click(slot1.getByRole("button", { name: "Clear Symbol for slot s1" }));
    await user.click(screen.getByRole("combobox", { name: "Symbol for slot s1" }));

    expect(await screen.findByText(/archive unreachable/i)).toBeInTheDocument();
  });

  it("recognizes a remembered instrument that stopped being archived, leaving other slots alone", async () => {
    fakeArchive.pairs = fakeArchive.pairs.filter((p) => p.symbol !== "US100");
    renderGrid();

    const slot1 = within(screen.getByTestId("slot-s1"));
    expect(await slot1.findByText(/no longer archived/i)).toBeInTheDocument();
    expect(slot1.getByText("US100")).toBeInTheDocument();

    expect(within(screen.getByTestId("slot-s2")).getByText("GOLD")).toBeInTheDocument();
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

  it("shares one connection between two slots on the same pair, and frees it with the last", () => {
    const sockets: FakeSocket[] = [];
    const hub = new SocketHub(
      (symbol, resolution) => `ws://test/ws/candles?symbol=${symbol}&resolution=${resolution}`,
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

  it("opens at most one connection per pair for a full 3x2 of distinct pairs", () => {
    const sockets: FakeSocket[] = [];
    const hub = new SocketHub(
      (symbol, resolution) => `ws://test/ws/candles?symbol=${symbol}&resolution=${resolution}`,
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

    expect(sockets).toHaveLength(6);
    expect(hub.activeConnectionCount()).toBe(6);

    for (const unsub of unsubs) unsub();
    expect(hub.activeConnectionCount()).toBe(0);
    expect(sockets.every((s) => s.closed)).toBe(true);
  });
});
