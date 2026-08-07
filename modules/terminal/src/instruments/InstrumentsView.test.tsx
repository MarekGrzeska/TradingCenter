import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import type { Instrument } from "../data/types";
import type { MarketDataSource } from "../data/source";

// Drives search results by hand so debounce and out-of-order answers are
// testable rather than incidental.
class SearchableSource implements MarketDataSource {
  readonly id = "mock" as const;
  searchCalls: string[] = [];
  listCalls = 0;

  private pending: Array<{ resolve(v: Instrument[]): void; reject(e: Error): void }> = [];
  private listResult: { instruments: Instrument[]; count: number; truncated: boolean } = {
    instruments: [],
    count: 0,
    truncated: false,
  };

  setCatalogue(instruments: Instrument[], truncated = false) {
    this.listResult = { instruments, count: instruments.length, truncated };
  }

  searchInstruments(query: string): Promise<Instrument[]> {
    this.searchCalls.push(query);
    return new Promise((resolve, reject) => this.pending.push({ resolve, reject }));
  }

  async listInstruments() {
    this.listCalls++;
    return this.listResult;
  }

  async history() {
    return [];
  }

  async ping() {}

  subscribe() {
    return () => {};
  }

  resolveSearch(index: number, instruments: Instrument[]) {
    this.pending[index]?.resolve(instruments);
  }

  rejectSearch(index: number, message: string) {
    this.pending[index]?.reject(new Error(message));
  }
}

let source: SearchableSource;

vi.mock("../data/sourceStore", () => ({
  sourceStore: {
    subscribe: () => () => {},
    getSnapshot: () => source,
    getSourceId: () => "mock" as const,
    setSource: () => {},
  },
}));

const { InstrumentsView } = await import("./InstrumentsView");
const { gridStore } = await import("../grid/gridStore");

function instrument(symbol: string, over: Partial<Instrument> = {}): Instrument {
  return {
    symbol,
    name: `${symbol} name`,
    assetClass: "INDICES",
    tradeable: true,
    bid: 1,
    ask: 2,
    ...over,
  };
}

function renderView() {
  return render(
    <MemoryRouter initialEntries={["/instruments"]}>
      <Routes>
        <Route path="/instruments" element={<InstrumentsView />} />
        <Route path="/graph" element={<div>graph tab</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  source = new SearchableSource();
  window.localStorage.clear();
  gridStore.setActiveSlot("s1");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Instruments search (terminal-instruments spec)", () => {
  it("does not issue a request per keystroke", async () => {
    // No fake timers: userEvent's own waits and a faked clock deadlock each
    // other. `delay: null` types all four characters faster than the 250 ms
    // debounce, which is exactly the condition being tested.
    const user = userEvent.setup({ delay: null });
    renderView();

    await user.type(screen.getByLabelText("Search instruments"), "gold");
    expect(source.searchCalls).toHaveLength(0);

    // Four keystrokes, one request — for the final query, not a prefix.
    await waitFor(() => expect(source.searchCalls).toEqual(["gold"]));
  });

  it("shows symbol, name, class and tradeability for each hit", async () => {
    const user = userEvent.setup();
    renderView();
    await user.type(screen.getByLabelText("Search instruments"), "gold");

    await waitFor(() => expect(source.searchCalls).toHaveLength(1));
    source.resolveSearch(0, [
      instrument("GOLD", { name: "Gold", assetClass: "COMMODITIES", bid: 2400.1, ask: 2400.4 }),
    ]);

    const row = await screen.findByText("GOLD");
    const cells = row.closest("tr")!;
    expect(within(cells).getByText("Gold")).toBeInTheDocument();
    expect(within(cells).getByText("COMMODITIES")).toBeInTheDocument();
    expect(within(cells).getByText("2400.1")).toBeInTheDocument();
    expect(within(cells).getByText("yes")).toBeInTheDocument();
  });

  it("distinguishes no matches from a failed search", async () => {
    const user = userEvent.setup();
    const { unmount } = renderView();

    await user.type(screen.getByLabelText("Search instruments"), "zzz");
    await waitFor(() => expect(source.searchCalls).toHaveLength(1));
    source.resolveSearch(0, []);
    expect(await screen.findByText(/nothing matches/i)).toBeInTheDocument();

    unmount();
    source = new SearchableSource();
    renderView();

    await user.type(screen.getByLabelText("Search instruments"), "gold");
    await waitFor(() => expect(source.searchCalls).toHaveLength(1));
    source.rejectSearch(0, "gateway unreachable");
    expect(await screen.findByText(/search failed: gateway unreachable/i)).toBeInTheDocument();
  });

  it("a slow answer to an earlier query never overwrites the current one", async () => {
    const user = userEvent.setup();
    renderView();
    const field = screen.getByLabelText("Search instruments");

    await user.type(field, "gol");
    await waitFor(() => expect(source.searchCalls).toHaveLength(1));

    await user.clear(field);
    await user.type(field, "btc");
    await waitFor(() => expect(source.searchCalls).toHaveLength(2));

    // The current query answers first, then the abandoned one arrives late.
    source.resolveSearch(1, [instrument("BTCUSD")]);
    expect(await screen.findByText("BTCUSD")).toBeInTheDocument();

    source.resolveSearch(0, [instrument("GOLD")]);
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByText("BTCUSD")).toBeInTheDocument();
    expect(screen.queryByText("GOLD")).not.toBeInTheDocument();
  });
});

describe("Instruments → grid (terminal-instruments spec)", () => {
  it("puts the chosen instrument in the active slot and shows the chart", async () => {
    const user = userEvent.setup();
    gridStore.setActiveSlot("s3");
    renderView();

    await user.type(screen.getByLabelText("Search instruments"), "tsla");
    await waitFor(() => expect(source.searchCalls).toHaveLength(1));
    source.resolveSearch(0, [instrument("TSLA")]);

    await user.click(await screen.findByText("TSLA"));

    expect(gridStore.getSnapshot().slots.s3.symbol).toBe("TSLA");
    expect(screen.getByText("graph tab")).toBeInTheDocument();
  });

  it("charts a non-tradeable instrument, flagging that it cannot be traded", async () => {
    const user = userEvent.setup();
    renderView();

    await user.type(screen.getByLabelText("Search instruments"), "idx");
    await waitFor(() => expect(source.searchCalls).toHaveLength(1));
    source.resolveSearch(0, [instrument("IDX1", { tradeable: false })]);

    expect(await screen.findByText(/not tradeable/i)).toBeInTheDocument();

    await user.click(screen.getByText("IDX1"));
    expect(gridStore.getSnapshot().slots.s1.symbol).toBe("IDX1");
  });
});

describe("Instruments catalogue", () => {
  it("warns when the catalogue came back truncated", async () => {
    source.setCatalogue([instrument("US100"), instrument("GOLD")], true);
    renderView();
    expect(await screen.findByText(/catalogue was cut short/i)).toBeInTheDocument();
  });

  it("reports the count without a warning when complete", async () => {
    source.setCatalogue([instrument("US100"), instrument("GOLD")], false);
    renderView();
    expect(await screen.findByText(/2 instruments/i)).toBeInTheDocument();
    expect(screen.queryByText(/cut short/i)).not.toBeInTheDocument();
  });
});
