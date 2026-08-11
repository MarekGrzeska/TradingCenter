import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DISMISS_AFTER_MS, createToastStore } from "./toastStore";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("toastStore", () => {
  it("shows what it was given, and tells subscribers", () => {
    const store = createToastStore();
    const listener = vi.fn();
    store.subscribe(listener);

    store.show({ key: "a", severity: "error", title: "Indicators unavailable", detail: "no series" });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).toEqual([
      { id: 1, key: "a", severity: "error", title: "Indicators unavailable", detail: "no series" },
    ]);
  });

  it("defaults to info, which is the severity that says nothing is wrong", () => {
    const store = createToastStore();
    store.show({ key: "a", title: "Saved" });
    expect(store.getSnapshot()[0]?.severity).toBe("info");
  });

  it("updates the toast already on screen instead of stacking the same thing again", () => {
    const store = createToastStore();
    // What a chart requerying its indicators on every candle close actually does.
    store.show({ key: "indicators:US100:HOUR", severity: "error", title: "first", detail: "why" });
    store.show({ key: "indicators:US100:HOUR", severity: "error", title: "second", detail: "why" });
    store.show({ key: "indicators:US100:HOUR", severity: "error", title: "third", detail: "why" });

    expect(store.getSnapshot()).toHaveLength(1);
    expect(store.getSnapshot()[0]?.title).toBe("third");
    // Same id, so React keeps the element and it does not flicker on every repeat.
    expect(store.getSnapshot()[0]?.id).toBe(1);
  });

  it("keeps two different keys apart — two slots can fail for two reasons", () => {
    const store = createToastStore();
    store.show({ key: "indicators:US100:HOUR", severity: "error", title: "one" });
    store.show({ key: "indicators:SILVER:DAY", severity: "error", title: "two" });

    expect(store.getSnapshot().map((t) => t.title)).toEqual(["one", "two"]);
  });

  it("removes itself after its own severity's delay", () => {
    const store = createToastStore();
    store.show({ key: "a", severity: "info", title: "Saved" });
    store.show({ key: "b", severity: "error", title: "Broken" });

    vi.advanceTimersByTime(DISMISS_AFTER_MS.info);
    expect(store.getSnapshot().map((t) => t.title)).toEqual(["Broken"]);

    vi.advanceTimersByTime(DISMISS_AFTER_MS.error - DISMISS_AFTER_MS.info);
    expect(store.getSnapshot()).toEqual([]);
  });

  it("restarts the clock when a repeat updates one, so a failing chart keeps it on screen", () => {
    const store = createToastStore();
    store.show({ key: "a", severity: "error", title: "Broken" });

    vi.advanceTimersByTime(DISMISS_AFTER_MS.error - 1_000);
    store.show({ key: "a", severity: "error", title: "Still broken" });
    vi.advanceTimersByTime(DISMISS_AFTER_MS.error - 1_000);

    expect(store.getSnapshot()).toHaveLength(1);
    vi.advanceTimersByTime(1_000);
    expect(store.getSnapshot()).toEqual([]);
  });

  it("can be dismissed by hand, and dismissing twice is not an error", () => {
    const store = createToastStore();
    store.show({ key: "a", title: "Saved" });
    const [toast] = store.getSnapshot();

    store.dismiss(toast!.id);
    store.dismiss(toast!.id);

    expect(store.getSnapshot()).toEqual([]);
  });

  it("drops the oldest rather than filling the screen with the chart it is talking about", () => {
    const store = createToastStore();
    for (const key of ["a", "b", "c", "d", "e"]) store.show({ key, title: key });

    expect(store.getSnapshot().map((t) => t.title)).toEqual(["b", "c", "d", "e"]);
  });

  it("does not resurrect a toast it dropped for being too old", () => {
    const store = createToastStore();
    for (const key of ["a", "b", "c", "d", "e"]) store.show({ key, title: key });

    // `a`'s own timer must have been cancelled with it; firing later, it would remove
    // whichever toast happened to hold its id by then — except ids are never reused, so
    // the visible failure is subtler: nothing at all, and a leaked timer.
    vi.advanceTimersByTime(DISMISS_AFTER_MS.info);
    expect(store.getSnapshot()).toEqual([]);
  });
});
