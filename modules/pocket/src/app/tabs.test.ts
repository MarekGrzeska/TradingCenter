import { describe, expect, it } from "vitest";
import { loadTab, saveTab, TABS } from "./tabs";

/** A phone is opened for seconds at a time, so the screen it opens on is the one it was closed on —
 *  and a value stored before a screen existed must not open on nothing. */
describe("the remembered tab", () => {
  it("comes back as it was saved", () => {
    const storage = new Map<string, string>();
    const store = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => void storage.set(key, value),
    };

    saveTab("social", store);

    expect(loadTab(store)).toBe("social");
  });

  it("falls back to the markets screen for a value this build does not know", () => {
    // A tab removed in a later build, read from a phone that stored it.
    const stored = { getItem: () => "a-screen-that-is-gone" };

    expect(loadTab(stored)).toBe("markets");
  });

  it("survives a browser that refuses to store anything", () => {
    const refusing = {
      getItem: () => {
        throw new Error("storage is disabled");
      },
    };

    expect(loadTab(refusing)).toBe("markets");
  });

  it("offers the three screens this app has", () => {
    expect([...TABS]).toEqual(["markets", "social", "agent"]);
  });
});
