import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMockSource, generateHistory } from "./mockSource";
import type { StreamEvent } from "./types";

const NOW_SECONDS = 1_786_113_300; // arbitrary fixed instant, same fixture as time.test.ts

describe("generateHistory", () => {
  it("is repeatable: same inputs, same series, every time", () => {
    const a = generateHistory("US100", "MINUTE_5", 50, NOW_SECONDS);
    const b = generateHistory("US100", "MINUTE_5", 50, NOW_SECONDS);
    expect(b).toEqual(a);
  });

  it("differs between symbols and between resolutions of the same symbol", () => {
    const us100 = generateHistory("US100", "MINUTE_5", 10, NOW_SECONDS);
    const gold = generateHistory("GOLD", "MINUTE_5", 10, NOW_SECONDS);
    const us100Minute = generateHistory("US100", "MINUTE", 10, NOW_SECONDS);
    expect(us100.map((b) => b.close)).not.toEqual(gold.map((b) => b.close));
    expect(us100.map((b) => b.close)).not.toEqual(us100Minute.map((b) => b.close));
  });

  it("never repaints bars a shorter request already returned", () => {
    const short = generateHistory("US100", "MINUTE_5", 20, NOW_SECONDS);
    const long = generateHistory("US100", "MINUTE_5", 200, NOW_SECONDS);
    const overlap = long.slice(-20);
    expect(overlap).toEqual(short);
  });

  it("produces ascending, evenly spaced, non-duplicated timestamps", () => {
    const bars = generateHistory("US100", "MINUTE_5", 30, NOW_SECONDS);
    for (let i = 1; i < bars.length; i++) {
      expect(bars[i].time - bars[i - 1].time).toBe(300);
    }
    expect(new Set(bars.map((b) => b.time)).size).toBe(bars.length);
  });

  it("marks every history bar settled, with a real volume", () => {
    const bars = generateHistory("US100", "MINUTE_5", 10, NOW_SECONDS);
    for (const bar of bars) {
      expect(bar.forming).toBe(false);
      expect(bar.volume).not.toBeNull();
    }
  });

  it("keeps every bar's own OHLC internally consistent", () => {
    const bars = generateHistory("BTCUSD", "HOUR", 100, NOW_SECONDS);
    for (const bar of bars) {
      expect(bar.high).toBeGreaterThanOrEqual(Math.max(bar.open, bar.close));
      expect(bar.low).toBeLessThanOrEqual(Math.min(bar.open, bar.close));
    }
  });
});

describe("createMockSource — catalog", () => {
  it("finds instruments by a case-insensitive symbol or name match", async () => {
    const source = createMockSource(() => NOW_SECONDS * 1000);
    const bySymbol = await source.searchInstruments("gold", new AbortController().signal);
    expect(bySymbol.map((i) => i.symbol)).toEqual(["GOLD"]);

    const byName = await source.searchInstruments("bitcoin", new AbortController().signal);
    expect(byName.map((i) => i.symbol)).toEqual(["BTCUSD"]);
  });

  it("lists the full catalog, never truncated", async () => {
    const source = createMockSource(() => NOW_SECONDS * 1000);
    const page = await source.listInstruments(new AbortController().signal);
    expect(page.truncated).toBe(false);
    expect(page.count).toBe(page.instruments.length);
    expect(page.count).toBeGreaterThan(0);
  });
});

describe("createMockSource — subscribe", () => {
  let currentMs: number;
  let now: () => number;

  function advance(ms: number) {
    currentMs += ms;
    vi.advanceTimersByTime(ms);
  }

  beforeEach(() => {
    vi.useFakeTimers();
    currentMs = NOW_SECONDS * 1000;
    now = () => currentMs;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends connected status and an initial forming bar right away", () => {
    const source = createMockSource(now);
    const events: StreamEvent[] = [];
    source.subscribe("US100", "MINUTE_5", (e) => events.push(e));

    expect(events[0]).toEqual({ kind: "status", state: "connected" });
    expect(events[1].kind).toBe("bar");
    expect((events[1] as { kind: "bar"; bar: { forming: boolean } }).bar.forming).toBe(true);
  });

  it("shares one interval timer between subscribers to the same pair", () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const source = createMockSource(now);
    source.subscribe("US100", "MINUTE_5", () => {});
    source.subscribe("US100", "MINUTE_5", () => {});
    expect(setIntervalSpy).toHaveBeenCalledTimes(1);
  });

  it("opens a separate timer per distinct pair", () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const source = createMockSource(now);
    source.subscribe("US100", "MINUTE_5", () => {});
    source.subscribe("GOLD", "MINUTE_5", () => {});
    expect(setIntervalSpy).toHaveBeenCalledTimes(2);
  });

  it("clears the timer only once the last subscriber leaves", () => {
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    const source = createMockSource(now);
    const unsubA = source.subscribe("US100", "MINUTE_5", () => {});
    const unsubB = source.subscribe("US100", "MINUTE_5", () => {});
    unsubA();
    expect(clearIntervalSpy).not.toHaveBeenCalled();
    unsubB();
    expect(clearIntervalSpy).toHaveBeenCalledTimes(1);
  });

  it("seals the old period with a settled bar before the new period's forming bar", () => {
    const source = createMockSource(now);
    const events: StreamEvent[] = [];
    // Start exactly on a MINUTE_5 boundary so the next tick that crosses 300s
    // is unambiguous.
    currentMs = Math.floor(NOW_SECONDS / 300) * 300 * 1000;
    source.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    events.length = 0; // drop the initial snapshot; only ticks matter below

    advance(300_000); // cross exactly one period boundary
    const bars = events.filter((e) => e.kind === "bar").map((e) => e.bar);
    const sealedIndex = bars.findIndex((b) => !b.forming);
    expect(sealedIndex).toBeGreaterThanOrEqual(0);
    expect(bars[sealedIndex + 1]?.forming).toBe(true);
    expect(bars[sealedIndex + 1]?.time).toBeGreaterThan(bars[sealedIndex].time);
  });

  it("a live forming bar continues from the same value history() would return next", async () => {
    currentMs = Math.floor(NOW_SECONDS / 300) * 300 * 1000;
    const source = createMockSource(now);

    const beforeHistory = await source.history(
      { symbol: "US100", resolution: "MINUTE_5", count: 1 },
      new AbortController().signal,
    );
    const lastSettledClose = beforeHistory[0].close;

    const events: StreamEvent[] = [];
    source.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    const firstForming = events.find((e) => e.kind === "bar")! as { kind: "bar"; bar: { open: number } };
    expect(firstForming.bar.open).toBe(lastSettledClose);
  });
});
