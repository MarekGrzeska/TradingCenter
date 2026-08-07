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

  it("assigns an instrument to whichever slot is active", () => {
    const store = createGridStore(memoryStorage());
    store.setActiveSlot("s3");
    const landed = store.assignToActiveSlot("TSLA");

    expect(landed).toBe("s3");
    expect(store.getSnapshot().slots.s3.symbol).toBe("TSLA");
  });
});
