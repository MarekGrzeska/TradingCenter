import { describe, expect, it } from "vitest";
import { UNGROUPED, UNGROUPED_LABEL, groupKeys, loadFilters, saveFilters, sections } from "./grouping";
import { anEvent } from "../test/builders";

const politics = anEvent({ providerEventId: "a", title: "B event", group: "Politics" });
const macro = anEvent({ providerEventId: "b", title: "A event", group: "Macro" });
const loose = anEvent({ providerEventId: "c", title: "C event", group: null });

describe("the chips", () => {
  it("include a group the archive knows before anything is filed under it", () => {
    expect(groupKeys([politics], ["Politics", "Sport"])).toEqual(["Politics", "Sport"]);
  });

  it("keep the ungrouped leftover last", () => {
    expect(groupKeys([loose, politics])).toEqual(["Politics", UNGROUPED]);
  });
});

describe("the sections a screen is drawn from", () => {
  it("sorts events inside a group by title", () => {
    const [section] = sections([politics, anEvent({ providerEventId: "d", title: "A", group: "Politics" })], {});
    expect(section.events.map((event) => event.title)).toEqual(["A", "B event"]);
  });

  it("labels the leftover rather than showing an empty heading", () => {
    const [section] = sections([loose], {});
    expect(section.label).toBe(UNGROUPED_LABEL);
  });

  it("drops a group switched off, and shows one it has never heard of", () => {
    const visible = sections([politics, macro], { Politics: false });
    expect(visible.map((section) => section.key)).toEqual(["Macro"]);
  });
});

describe("what survives a reload", () => {
  it("is the map of switches, round-tripped", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    };

    saveFilters({ Politics: false }, storage);
    expect(loadFilters(storage)).toEqual({ Politics: false });
  });

  it("is nothing at all when the stored value is not a map of switches", () => {
    const storage = { getItem: () => "[\"Politics\"]" };
    expect(loadFilters(storage)).toEqual({});
  });
});
