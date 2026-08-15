import { describe, expect, it, vi } from "vitest";
import { createGridStore, STORAGE_KEY } from "./gridStore";
import { defaultGridConfig, parseGridConfig } from "./model";

function memoryStorage(seed?: string) {
  const map = new Map<string, string>();
  if (seed !== undefined) map.set(STORAGE_KEY, seed);
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    raw: map,
  };
}

describe("parseGridConfig (terminal-grid spec, persistence guard)", () => {
  it("accepts a config it just produced", () => {
    const config = defaultGridConfig();
    expect(parseGridConfig(JSON.parse(JSON.stringify(config)))).toEqual(config);
  });

  it.each([
    ["not an object", 42],
    ["null", null],
    ["an unknown layout", { ...defaultGridConfig(), layout: "9x9" }],
    ["an unknown active slot", { ...defaultGridConfig(), activeSlot: "s99" }],
    ["missing slots", { layout: "2x2", activeSlot: "s1" }],
    [
      "a slot with an unsupported resolution",
      {
        ...defaultGridConfig(),
        slots: {
          ...defaultGridConfig().slots,
          s1: { symbol: "US100", resolution: "FORTNIGHT" },
        },
      },
    ],
    [
      "a slot with a non-numeric indicator param",
      {
        ...defaultGridConfig(),
        slots: {
          ...defaultGridConfig().slots,
          s1: {
            symbol: "US100",
            resolution: "MINUTE_5",
            indicators: [{ key: "ema", id: "ema", params: { period: "20" }, color: null }],
          },
        },
      },
    ],
    [
      "a slot missing entirely",
      (() => {
        const config = defaultGridConfig() as unknown as { slots: Record<string, unknown> };
        const slots = { ...config.slots };
        delete slots.s6;
        return { ...config, slots };
      })(),
    ],
  ])("rejects %s", (_label, value) => {
    expect(parseGridConfig(value)).toBeNull();
  });

  it("reads a slot saved before indicators had instances or colours", () => {
    const saved = {
      ...defaultGridConfig(),
      slots: {
        ...defaultGridConfig().slots,
        s1: {
          symbol: "US100",
          resolution: "MINUTE_5",
          indicators: [{ id: "ema", params: { period: 20 } }, { id: "rsi", params: {} }],
        },
      },
    };

    const parsed = parseGridConfig(saved);

    // Every indicator survives; the two fields it never had are filled in, not held
    // against it (terminal-grid spec, "Slot zapisany przed instancjami i kolorami").
    expect(parsed?.slots.s1.indicators).toEqual([
      expect.objectContaining({ id: "ema", params: { period: 20 }, color: null }),
      expect.objectContaining({ id: "rsi", params: {}, color: null }),
    ]);
    const [first, second] = parsed?.slots.s1.indicators ?? [];
    expect(first.key).toEqual(expect.any(String));
    expect(first.key).not.toBe(second.key);
  });

  it("keeps three instances of one entry, each with its own params and colour", () => {
    const saved = {
      ...defaultGridConfig(),
      slots: {
        ...defaultGridConfig().slots,
        s1: {
          symbol: "US100",
          resolution: "MINUTE_5",
          indicators: [
            { key: "a", id: "ema", params: { period: 20 }, color: "--color-accent" },
            { key: "b", id: "ema", params: { period: 50 }, color: "--color-indicator-5" },
            { key: "c", id: "ema", params: { period: 200 }, color: null },
          ],
        },
      },
    };

    expect(parseGridConfig(saved)?.slots.s1.indicators).toEqual(saved.slots.s1.indicators);
  });

  it("reads a colour the palette no longer offers as no colour, rather than losing the slot", () => {
    const saved = {
      ...defaultGridConfig(),
      slots: {
        ...defaultGridConfig().slots,
        s1: {
          symbol: "US100",
          resolution: "MINUTE_5",
          indicators: [{ key: "a", id: "ema", params: { period: 20 }, color: "#ff00ff" }],
        },
      },
    };

    expect(parseGridConfig(saved)?.slots.s1.indicators).toEqual([
      { key: "a", id: "ema", params: { period: 20 }, color: null },
    ]);
  });
});

describe("createGridStore", () => {
  it("starts from defaults when nothing is stored", () => {
    const store = createGridStore(memoryStorage());
    expect(store.getSnapshot()).toEqual(defaultGridConfig());
  });

  it("restores a previously saved config", () => {
    const storage = memoryStorage();
    const first = createGridStore(storage);
    first.setLayout("3x2");
    first.setSlotSymbol("s5", "SILVER");

    const second = createGridStore(storage);
    expect(second.getSnapshot().layout).toBe("3x2");
    expect(second.getSnapshot().slots.s5.symbol).toBe("SILVER");
  });

  it("falls back to defaults on an unreadable saved config rather than refusing to start", () => {
    const store = createGridStore(memoryStorage("{ this is not json"));
    expect(store.getSnapshot()).toEqual(defaultGridConfig());
  });

  it("falls back to defaults on a structurally wrong saved config", () => {
    const store = createGridStore(memoryStorage(JSON.stringify({ layout: "9x9" })));
    expect(store.getSnapshot()).toEqual(defaultGridConfig());
  });

  it("survives a storage that throws (private-mode Safari)", () => {
    const hostile = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    const store = createGridStore(hostile);
    expect(store.getSnapshot()).toEqual(defaultGridConfig());
    expect(() => store.setLayout("1x1")).not.toThrow();
    expect(store.getSnapshot().layout).toBe("1x1");
  });

  it("restores a saved slot's indicators the same way it restores symbol and resolution", () => {
    const storage = memoryStorage();
    const first = createGridStore(storage);
    first.setSlotIndicators("s2", [{ key: "ema", id: "ema", params: { period: 20 }, color: null }]);

    const second = createGridStore(storage);
    expect(second.getSnapshot().slots.s2.indicators).toEqual([
      { key: "ema", id: "ema", params: { period: 20 }, color: null },
    ]);
  });

  it("keeps hidden slots' configuration when shrinking the layout", () => {
    const store = createGridStore(memoryStorage());
    store.setLayout("3x2");
    store.setSlotSymbol("s6", "SILVER");

    store.setLayout("2x2"); // s5 and s6 now hidden
    store.setLayout("3x2"); // and back

    expect(store.getSnapshot().slots.s6.symbol).toBe("SILVER");
  });

  it("notifies subscribers and stops after unsubscribe", () => {
    const store = createGridStore(memoryStorage());
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.setLayout("1x1");
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    store.setLayout("2x2");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not notify when setting the layout already in use", () => {
    const store = createGridStore(memoryStorage());
    const listener = vi.fn();
    store.subscribe(listener);
    store.setLayout(store.getSnapshot().layout);
    expect(listener).not.toHaveBeenCalled();
  });
});

describe("createGridStore focus requests", () => {
  const focus = { from: 1, to: 2, around: null, bars: null, lastBars: null };

  it("has no request for a slot until one is set", () => {
    const store = createGridStore(memoryStorage());
    expect(store.getFocusRequest("s1")).toBeNull();
  });

  it("returns what was set for that slot", () => {
    const store = createGridStore(memoryStorage());
    store.setFocusRequest("s1", focus);
    expect(store.getFocusRequest("s1")).toEqual(focus);
  });

  it("clears on request, and stays cleared", () => {
    const store = createGridStore(memoryStorage());
    store.setFocusRequest("s1", focus);
    store.clearFocusRequest("s1");
    expect(store.getFocusRequest("s1")).toBeNull();
  });

  it("notifies focus listeners on set and on clear, not the config listeners", () => {
    const store = createGridStore(memoryStorage());
    const focusListener = vi.fn();
    const configListener = vi.fn();
    store.subscribeFocusRequest(focusListener);
    store.subscribe(configListener);

    store.setFocusRequest("s1", focus);
    store.clearFocusRequest("s1");

    expect(focusListener).toHaveBeenCalledTimes(2);
    expect(configListener).not.toHaveBeenCalled();
  });

  it("does not notify when clearing a slot with no request", () => {
    const store = createGridStore(memoryStorage());
    const listener = vi.fn();
    store.subscribeFocusRequest(listener);
    store.clearFocusRequest("s1");
    expect(listener).not.toHaveBeenCalled();
  });

  it("keeps one slot's request independent of another's", () => {
    const store = createGridStore(memoryStorage());
    store.setFocusRequest("s1", focus);
    store.setFocusRequest("s2", { ...focus, from: 99 });

    expect(store.getFocusRequest("s1")).toEqual(focus);
    expect(store.getFocusRequest("s2")?.from).toBe(99);
  });

  it("never reaches storage: setting the config afterwards saves no trace of it", () => {
    const storage = memoryStorage();
    const store = createGridStore(storage);
    store.setFocusRequest("s1", focus);
    store.setLayout("1x1"); // the only thing that writes to storage

    expect(storage.raw.get(STORAGE_KEY)).not.toContain("from");
  });

  it("does not survive a reload — it is not part of the persisted config", () => {
    const storage = memoryStorage();
    const first = createGridStore(storage);
    first.setFocusRequest("s1", focus);
    first.setLayout("1x1"); // forces a write, so there is something to reload

    const second = createGridStore(storage);
    expect(second.getFocusRequest("s1")).toBeNull();
  });
});
