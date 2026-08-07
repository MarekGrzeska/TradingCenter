import { describe, expect, it, vi } from "vitest";
import { createSourceStore } from "./sourceStore";
import type { MarketDataSource } from "./source";

function fakeSource(id: MarketDataSource["id"]): MarketDataSource {
  return {
    id,
    searchInstruments: async () => [],
    listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
    history: async () => [],
    ping: async () => {},
    subscribe: () => () => {},
  };
}

describe("createSourceStore", () => {
  it("builds only the default source at construction time", () => {
    const build = vi.fn(fakeSource);
    createSourceStore("mock", build);
    expect(build).toHaveBeenCalledTimes(1);
    expect(build).toHaveBeenCalledWith("mock");
  });

  it("switches the snapshot and notifies subscribers", () => {
    const build = vi.fn(fakeSource);
    const store = createSourceStore("mock", build);
    const listener = vi.fn();
    store.subscribe(listener);

    store.setSource("gateway");

    expect(store.getSourceId()).toBe("gateway");
    expect(store.getSnapshot().id).toBe("gateway");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(build).toHaveBeenCalledWith("gateway");
  });

  it("does nothing on setSource to the already-active id", () => {
    const build = vi.fn(fakeSource);
    const store = createSourceStore("mock", build);
    const listener = vi.fn();
    store.subscribe(listener);
    const before = store.getSnapshot();

    store.setSource("mock");

    expect(store.getSnapshot()).toBe(before);
    expect(listener).not.toHaveBeenCalled();
    expect(build).toHaveBeenCalledTimes(1); // only the initial build
  });

  it("stops notifying an unsubscribed listener", () => {
    const store = createSourceStore("mock", fakeSource);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();

    store.setSource("gateway");

    expect(listener).not.toHaveBeenCalled();
  });
});
