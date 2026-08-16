import { describe, expect, it, vi } from "vitest";
import type { AgentApi, AgentChartDrawing, AgentDrawingPatch } from "./agentApi";
import { createDrawingsStore, describeDrawingsChange } from "./drawingsStore";
import { MarketDataError } from "../data/types";

function level(
  id: number,
  price: number,
  symbol = "US100",
  hidden = false,
): AgentChartDrawing {
  return {
    id,
    symbol,
    geometry: { kind: "level", price, at: null },
    label: null,
    color: null,
    hidden,
    createdAt: 1767398400,
    updatedAt: 1767398400,
  };
}

/** Only the three methods this store calls — everything else on `AgentApi` throws, so a
 *  test that reaches for one says so rather than quietly answering. */
function fakeApi(overrides: Partial<AgentApi> = {}): AgentApi {
  const base = {
    listDrawings: vi.fn(async () => [] as AgentChartDrawing[]),
    patchDrawing: vi.fn(async () => level(1, 1)),
    deleteDrawing: vi.fn(async () => {}),
  };
  return new Proxy({ ...base, ...overrides } as AgentApi, {
    get(target, key) {
      const value = Reflect.get(target, key);
      if (value === undefined) throw new Error(`${String(key)} is not used by drawingsStore`);
      return value;
    },
  });
}

describe("drawingsStore", () => {
  it("reads a symbol the first time anyone asks, and not again", async () => {
    const listDrawings = vi.fn(async () => [level(1, 21500)]);
    const store = createDrawingsStore(fakeApi({ listDrawings }));

    store.ensureLoaded("US100");
    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    expect(listDrawings).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().US100.drawings.map((d) => d.id)).toEqual([1]);
  });

  it("keeps one instrument's objects out of another's", async () => {
    const store = createDrawingsStore(
      fakeApi({
        listDrawings: vi.fn(async (symbol: string) =>
          symbol === "US100" ? [level(1, 21500)] : [level(2, 2400, "GOLD")],
        ),
      }),
    );

    store.ensureLoaded("US100");
    store.ensureLoaded("GOLD");
    await vi.waitFor(() => expect(store.getSnapshot().GOLD?.status).toBe("ready"));

    expect(store.getSnapshot().US100.drawings.map((d) => d.id)).toEqual([1]);
    expect(store.getSnapshot().GOLD.drawings.map((d) => d.id)).toEqual([2]);
  });

  it("a failed read keeps what was already drawn and says what went wrong", async () => {
    // `terminal-chart` spec, "Nieudany odczyt obiektów": the chart keeps drawing, and the
    // failure is said separately rather than by an empty list.
    let answer: AgentChartDrawing[] | Error = [level(1, 21500)];
    const store = createDrawingsStore(
      fakeApi({
        listDrawings: vi.fn(async () => {
          if (answer instanceof Error) throw answer;
          return answer;
        }),
      }),
    );

    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    answer = new MarketDataError("unknown", "agent is not reachable");
    await store.refresh("US100");

    expect(store.getSnapshot().US100.status).toBe("error");
    expect(store.getSnapshot().US100.drawings.map((d) => d.id)).toEqual([1]);
    expect(store.getSnapshot().US100.error).toContain("not reachable");
  });

  it("a refresh answers what appeared and what went", async () => {
    let answer = [level(1, 21500)];
    const store = createDrawingsStore(fakeApi({ listDrawings: vi.fn(async () => answer) }));

    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    answer = [level(2, 21600), level(3, 21400)];
    expect(await store.refresh("US100")).toEqual({ added: 2, removed: 1 });
  });

  it("refreshAll reads every symbol it has an entry for", async () => {
    // The agent may have drawn on an instrument no slot is showing — every loaded symbol
    // is read after a turn, not only the active one.
    const listDrawings = vi.fn(async (_symbol: string) => [] as AgentChartDrawing[]);
    const store = createDrawingsStore(fakeApi({ listDrawings }));

    store.ensureLoaded("US100");
    store.ensureLoaded("GOLD");
    await vi.waitFor(() => expect(listDrawings).toHaveBeenCalledTimes(2));

    await store.refreshAll();
    expect(listDrawings.mock.calls.map((call) => call[0]).slice(2).sort()).toEqual(["GOLD", "US100"]);
  });

  it("a removal re-reads rather than trusting the copy in hand", async () => {
    let answer = [level(1, 21500), level(2, 21400)];
    const deleteDrawing = vi.fn(async (id: number) => {
      answer = answer.filter((drawing) => drawing.id !== id);
    });
    const store = createDrawingsStore(fakeApi({ listDrawings: vi.fn(async () => answer), deleteDrawing }));

    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    expect(await store.remove(1)).toBeNull();
    expect(store.getSnapshot().US100.drawings.map((d) => d.id)).toEqual([2]);
  });

  it("a failed removal leaves the list alone and answers the sentence to show", async () => {
    const store = createDrawingsStore(
      fakeApi({
        listDrawings: vi.fn(async () => [level(1, 21500)]),
        deleteDrawing: vi.fn(async () => {
          throw new MarketDataError("not-found", "no drawing #1");
        }),
      }),
    );

    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    expect(await store.remove(1)).toContain("no drawing #1");
    expect(store.getSnapshot().US100.drawings.map((d) => d.id)).toEqual([1]);
  });

  it("a correction re-reads the symbol the drawing belongs to", async () => {
    let answer = [level(1, 21500)];
    const patchDrawing = vi.fn(async (id: number, patch: AgentDrawingPatch) => {
      answer = [level(id, patch.price ?? 0)];
      return answer[0];
    });
    const store = createDrawingsStore(fakeApi({ listDrawings: vi.fn(async () => answer), patchDrawing }));

    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100?.status).toBe("ready"));

    expect(await store.patch(1, { price: 21550 })).toBeNull();
    const [drawing] = store.getSnapshot().US100.drawings;
    expect(drawing.geometry).toEqual({ kind: "level", price: 21550, at: null });
  });
});

describe("describeDrawingsChange", () => {
  it("says nothing when nothing changed", () => {
    expect(describeDrawingsChange({ added: 0, removed: 0 })).toBeNull();
  });

  it("names what appeared", () => {
    expect(describeDrawingsChange({ added: 1, removed: 0 })).toBe(
      "The agent drew 1 object on the chart.",
    );
  });

  it("names both sides of a move", () => {
    expect(describeDrawingsChange({ added: 2, removed: 1 })).toBe(
      "The agent drew 2 objects and removed 1 on the chart.",
    );
  });
});

describe("drawingsStore — hiding", () => {
  it("hides through patch and re-reads, rather than editing the copy in hand", async () => {
    const patchDrawing = vi.fn(async () => level(1, 21500, "US100", true));
    const listDrawings = vi
      .fn()
      .mockResolvedValueOnce([level(1, 21500)])
      .mockResolvedValueOnce([level(1, 21500, "US100", true)]);
    const store = createDrawingsStore(fakeApi({ listDrawings, patchDrawing }));
    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100.status).toBe("ready"));

    expect(await store.patch(1, { hidden: true })).toBeNull();

    expect(patchDrawing).toHaveBeenCalledWith(1, { hidden: true }, expect.anything());
    // The module is the record; this is what it answered on the second read.
    expect(store.getSnapshot().US100.drawings[0].hidden).toBe(true);
  });

  it("says a failed hiding failed and leaves the list as it was", async () => {
    const patchDrawing = vi.fn(async () => {
      throw new MarketDataError("not-found", "no drawing #1");
    });
    const listDrawings = vi.fn(async () => [level(1, 21500)]);
    const store = createDrawingsStore(fakeApi({ listDrawings, patchDrawing }));
    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100.status).toBe("ready"));

    expect(await store.patch(1, { hidden: true })).toBe("no drawing #1");
    expect(store.getSnapshot().US100.drawings[0].hidden).toBe(false);
  });

  it("counts a hidden object as still there, not as removed", async () => {
    // The panel's sentence after a turn is about what appeared and went; hiding is
    // neither, and reporting it as a removal would be a claim the record contradicts.
    const listDrawings = vi
      .fn()
      .mockResolvedValueOnce([level(1, 21500)])
      .mockResolvedValueOnce([level(1, 21500, "US100", true)]);
    const store = createDrawingsStore(fakeApi({ listDrawings }));
    store.ensureLoaded("US100");
    await vi.waitFor(() => expect(store.getSnapshot().US100.status).toBe("ready"));

    expect(await store.refresh("US100")).toEqual({ added: 0, removed: 0 });
  });
});
