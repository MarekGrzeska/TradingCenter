import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

/**
 * A grid of six charts, and one slot's change waking the other five.
 *
 * `Slot` used to subscribe to the whole grid configuration and `useSlotDrawings` to the
 * whole drawings snapshot, so changing one slot's resolution re-rendered every chart on
 * screen — including the ones drawing a different instrument entirely. `Chart` is the
 * most expensive component in the terminal to render, which is what makes this worth a
 * test rather than a comment: nothing in the rendered output says how many charts were
 * rebuilt, so nothing else here would ever fail if the subscriptions widened again.
 */

let renders: Record<string, number> = {};

vi.mock("../chart/Chart", () => ({
  Chart: ({ symbol }: { symbol: string | null }) => {
    const key = symbol ?? "empty";
    renders[key] = (renders[key] ?? 0) + 1;
    return <div data-testid={`chart-${key}`} />;
  },
}));

vi.mock("../data/marketData", () => ({
  marketData: {
    parts: [],
    searchInstruments: async () => [],
    listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
    history: async () => [],
    subscribe: () => () => {},
  },
  archive: { listPairs: async () => [] },
  indicators: undefined,
}));

vi.mock("../agent/drawingsStore", () => {
  // One frozen object, returned every time — `useSyncExternalStore` compares snapshots by
  // identity, and a fresh `{}` per call is an infinite render loop.
  const empty = Object.freeze({});
  return {
    drawingsStore: {
      subscribe: () => () => {},
      getSnapshot: () => empty,
      ensureLoaded: () => {},
      refresh: async () => ({ added: 0, removed: 0 }),
      refreshAll: async () => ({ added: 0, removed: 0 }),
      remove: async () => null,
      patch: async () => null,
    },
  };
});

const { GridView } = await import("./GridView");
const { gridStore } = await import("./gridStore");
const { defaultGridConfig, SLOT_IDS } = await import("./model");

beforeEach(() => {
  renders = {};
  window.localStorage.clear();
  // The store is a module singleton holding its state in memory, so clearing storage is
  // not enough to undo the previous test.
  const defaults = defaultGridConfig();
  gridStore.setLayout(defaults.layout);
  for (const slot of SLOT_IDS) {
    gridStore.clearSlotSymbol(slot);
    gridStore.setSlotResolution(slot, defaults.slots[slot].resolution);
    gridStore.setSlotIndicators(slot, []);
  }
});

describe("one slot changing does not re-render the others", () => {
  it("leaves the second chart alone when the first one's resolution changes", async () => {
    gridStore.setLayout("2x2");
    gridStore.setSlotSymbol("s1", "US100");
    gridStore.setSlotSymbol("s2", "GOLD");

    render(
      <MemoryRouter>
        <GridView />
      </MemoryRouter>,
    );
    const before = { ...renders };
    expect(before.US100).toBeGreaterThan(0);
    expect(before.GOLD).toBeGreaterThan(0);

    await act(async () => {
      gridStore.setSlotResolution("s1", "HOUR");
    });

    expect(renders.US100).toBeGreaterThan(before.US100);
    expect(renders.GOLD).toBe(before.GOLD);
  });

  it("leaves both charts alone when a focus request is made for neither", async () => {
    gridStore.setLayout("2x2");
    gridStore.setSlotSymbol("s1", "US100");
    gridStore.setSlotSymbol("s2", "GOLD");

    render(
      <MemoryRouter>
        <GridView />
      </MemoryRouter>,
    );
    const before = { ...renders };

    await act(async () => {
      gridStore.setFocusRequest("s3", { from: 1, to: 2, around: null, bars: null, lastBars: null });
    });

    expect(renders.US100).toBe(before.US100);
    expect(renders.GOLD).toBe(before.GOLD);
  });
});
