/**
 * What the agent set, applied to the slot the operator is on — once, in the bounds the
 * slot already has.
 *
 * `terminal-grid` spec, "Aktywny slot stosuje to, co ustawił agent"; `terminal-agent-chat`
 * spec, "Panel mówi, że wykres zmienił agent".
 */

import { beforeEach, describe, expect, it } from "vitest";

import type { AgentApi, AgentChartCommand } from "./agentApi";
import {
  CHART_CURSOR_KEY,
  activeChartSnapshot,
  describeChartControl,
  syncAgentChart,
} from "./chartControl";
import type { ArchiveAdmin } from "../data/source";
import type { Resolution, TrackedPair } from "../data/types";
import { createGridStore } from "../grid/gridStore";

function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map<string, string>(Object.entries(seed));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    raw: map,
  };
}

function pair(symbol: string, resolution: Resolution): TrackedPair {
  return {
    symbol,
    resolution,
    collection: "running",
    collectFrom: null,
    candleCount: 10,
    latestCandle: null,
    createdAt: 0,
  } as unknown as TrackedPair;
}

/** Answers the way the module does: a command only while the caller's cursor is behind
 *  it, and nothing once it has caught up. */
function fakeApi(command: AgentChartCommand | null, calls: number[] = []): AgentApi {
  return {
    chartCommand: async (after: number) => {
      calls.push(after);
      if (command === null || after >= command.sequence) return null;
      return command;
    },
  } as unknown as AgentApi;
}

function fakePairs(pairs: TrackedPair[] = [pair("US100", "MINUTE_5"), pair("US100", "HOUR")]): ArchiveAdmin {
  return { listPairs: async () => pairs } as unknown as ArchiveAdmin;
}

function command(over: Partial<AgentChartCommand> = {}): AgentChartCommand {
  return { sequence: 7, symbol: null, resolution: null, indicators: null, ...over };
}

describe("syncAgentChart", () => {
  let grid: ReturnType<typeof createGridStore>;
  let storage: ReturnType<typeof memoryStorage>;

  beforeEach(() => {
    storage = memoryStorage();
    grid = createGridStore(memoryStorage());
  });

  it("applies the indicators the agent set to the active slot, and leaves the others alone", async () => {
    grid.setActiveSlot("s2");
    const before = grid.getSnapshot().slots.s1.indicators;

    const result = await syncAgentChart({
      api: fakeApi(command({ indicators: [{ id: "ema", params: { period: 200 }, color: null }] })),
      grid,
      pairs: fakePairs(),
      storage,
    });

    expect(grid.getSnapshot().slots.s2.indicators).toEqual([
      expect.objectContaining({ id: "ema", params: { period: 200 }, color: null }),
    ]);
    expect(grid.getSnapshot().slots.s1.indicators).toEqual(before);
    expect(result).toEqual({ applied: ["EMA period 200"], skipped: [] });
  });

  it("hands each applied instance a key of its own", async () => {
    await syncAgentChart({
      api: fakeApi(
        command({
          indicators: [
            { id: "ema", params: { period: 20 }, color: null },
            { id: "ema", params: { period: 20 }, color: "--color-accent" },
          ],
        }),
      ),
      grid,
      pairs: fakePairs(),
      storage,
    });

    const [first, second] = grid.getSnapshot().slots[grid.getSnapshot().activeSlot].indicators;
    expect(first.key).not.toBe(second.key);
  });

  it("applies symbol and interval the archive collects", async () => {
    const result = await syncAgentChart({
      api: fakeApi(command({ symbol: "US100", resolution: "HOUR" })),
      grid,
      pairs: fakePairs(),
      storage,
    });

    const slot = grid.getSnapshot().slots[grid.getSnapshot().activeSlot];
    expect([slot.symbol, slot.resolution]).toEqual(["US100", "HOUR"]);
    expect(result?.applied).toEqual(["symbol US100", "interval HOUR"]);
  });

  it("skips a symbol the archive does not collect rather than drawing an empty chart", async () => {
    const before = grid.getSnapshot().slots[grid.getSnapshot().activeSlot].symbol;

    const result = await syncAgentChart({
      api: fakeApi(command({ symbol: "TSLA" })),
      grid,
      pairs: fakePairs(),
      storage,
    });

    expect(grid.getSnapshot().slots[grid.getSnapshot().activeSlot].symbol).toBe(before);
    expect(result?.skipped).toEqual(["TSLA is not collected"]);
    expect(describeChartControl(result)).toContain("Not applied");
  });

  it("skips an interval that symbol is not collected in", async () => {
    const result = await syncAgentChart({
      api: fakeApi(command({ symbol: "US100", resolution: "DAY" })),
      grid,
      pairs: fakePairs(),
      storage,
    });

    const slot = grid.getSnapshot().slots[grid.getSnapshot().activeSlot];
    expect(slot.symbol).toBe("US100");
    expect(slot.resolution).not.toBe("DAY");
    expect(result?.skipped).toEqual(["DAY is not collected for US100"]);
  });

  it("does not let a rejected symbol veto a resolution the slot's own symbol collects", async () => {
    const active = grid.getSnapshot().activeSlot;
    grid.setSlotSymbol(active, "US100");
    grid.setSlotResolution(active, "MINUTE_5");

    const result = await syncAgentChart({
      api: fakeApi(command({ symbol: "TSLA", resolution: "HOUR" })),
      grid,
      pairs: fakePairs(),
      storage,
    });

    const slot = grid.getSnapshot().slots[active];
    expect(slot.symbol).toBe("US100");
    expect(slot.resolution).toBe("HOUR");
    expect(result?.applied).toEqual(["interval HOUR"]);
    expect(result?.skipped).toEqual(["TSLA is not collected"]);
  });

  it("does not apply the same command twice", async () => {
    const asked: number[] = [];
    const api = fakeApi(command({ indicators: [{ id: "ema", params: {}, color: null }] }), asked);

    await syncAgentChart({ api, grid, pairs: fakePairs(), storage });
    // The operator removes it by hand; the next sync must not put it back.
    grid.setSlotIndicators(grid.getSnapshot().activeSlot, []);
    await syncAgentChart({ api, grid, pairs: fakePairs(), storage });

    expect(asked).toEqual([0, 7]);
    expect(grid.getSnapshot().slots[grid.getSnapshot().activeSlot].indicators).toEqual([]);
    expect(storage.raw.get(CHART_CURSOR_KEY)).toBe("7");
  });

  it("asks from the cursor it was left with, across a reload", async () => {
    const asked: number[] = [];
    await syncAgentChart({
      api: fakeApi(null, asked),
      grid,
      pairs: fakePairs(),
      storage: memoryStorage({ [CHART_CURSOR_KEY]: "12" }),
    });

    expect(asked).toEqual([12]);
  });

  it("leaves the chart and the cursor alone when the read fails", async () => {
    const api = {
      chartCommand: async () => {
        throw new Error("agent unreachable");
      },
    } as unknown as AgentApi;
    const before = grid.getSnapshot();

    const result = await syncAgentChart({ api, grid, pairs: fakePairs(), storage });

    expect(result).toBeNull();
    expect(grid.getSnapshot()).toEqual(before);
    expect(storage.raw.has(CHART_CURSOR_KEY)).toBe(false);
  });

  it("waits rather than guessing when the archive cannot say what it collects", async () => {
    const pairs = {
      listPairs: async () => {
        throw new Error("archive unreachable");
      },
    } as unknown as ArchiveAdmin;

    const result = await syncAgentChart({
      api: fakeApi(command({ symbol: "US100" })),
      grid,
      pairs,
      storage,
    });

    expect(result).toBeNull();
    // The cursor stays put, so the command is applied once the archive answers again.
    expect(storage.raw.has(CHART_CURSOR_KEY)).toBe(false);
  });

  it("says nothing when the agent set nothing", async () => {
    const result = await syncAgentChart({
      api: fakeApi(null),
      grid,
      pairs: fakePairs(),
      storage,
    });

    expect(result).toBeNull();
    expect(describeChartControl(result)).toBeNull();
  });
});

describe("activeChartSnapshot", () => {
  it("describes the active slot, indicators and all", () => {
    const grid = createGridStore(memoryStorage());
    grid.setActiveSlot("s1");
    grid.setSlotSymbol("s1", "US100");
    grid.setSlotResolution("s1", "HOUR");
    grid.setSlotIndicators("s1", [
      { key: "a", id: "ema", params: { period: 200 }, color: "--color-accent" },
    ]);

    expect(activeChartSnapshot(grid)).toEqual({
      symbol: "US100",
      resolution: "HOUR",
      indicators: [{ id: "ema", params: { period: 200 }, color: "--color-accent" }],
    });
  });

  it("sends nothing at all for a slot with no instrument", () => {
    const grid = createGridStore(memoryStorage());
    grid.setActiveSlot("s5"); // empty in the default layout
    grid.clearSlotSymbol("s5");

    expect(activeChartSnapshot(grid)).toBeNull();
  });
});
