import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MarketDataError, type Instrument, type PairCoverage, type Resolution, type TrackedPair } from "../data/types";

/**
 * A stand-in archive the test drives. It keeps a list, because half of what the
 * panel claims is about the list changing — a pair added appears, a pair
 * stopped disappears — and asserting that against a mock that always answers
 * the same thing would assert nothing.
 */
class FakeArchive {
  pairs: TrackedPair[] = [];
  coverageAnswer: PairCoverage | null = null;
  listFailure: Error | null = null;
  trackFailure: Error | null = null;
  trackCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  untrackCalls: Array<{ symbol: string; resolution: Resolution }> = [];

  listPairs = async () => {
    if (this.listFailure) throw this.listFailure;
    return [...this.pairs];
  };

  trackPair = async (symbol: string, resolution: Resolution) => {
    this.trackCalls.push({ symbol, resolution });
    if (this.trackFailure) throw this.trackFailure;
    const pair: TrackedPair = {
      symbol,
      resolution,
      addedAt: 1786113600,
      latestCandle: null,
      collection: "never_collected",
    };
    this.pairs = [...this.pairs, pair];
    return pair;
  };

  untrackPair = async (symbol: string, resolution: Resolution) => {
    this.untrackCalls.push({ symbol, resolution });
    this.pairs = this.pairs.filter(
      (pair) => !(pair.symbol === symbol && pair.resolution === resolution),
    );
  };

  coverage = async (symbol: string, resolution: Resolution): Promise<PairCoverage> =>
    this.coverageAnswer ?? { symbol, resolution, ranges: [], earliestReachable: null };
}

class FakeCatalogue {
  results: Instrument[] = [];

  searchInstruments = async (query: string) =>
    this.results.filter((instrument) =>
      instrument.symbol.toLowerCase().includes(query.toLowerCase()),
    );

  listInstruments = async () => ({ instruments: this.results, count: 0, truncated: false });
}

let fakeArchive: FakeArchive;
let catalogue: FakeCatalogue;

vi.mock("../data/marketData", () => ({
  // Getters, so each test's freshly built doubles are the ones the view reads.
  get archive() {
    return fakeArchive;
  },
  get marketData() {
    return catalogue;
  },
}));

const { ArchiveView } = await import("./ArchiveView");

function pair(over: Partial<TrackedPair> = {}): TrackedPair {
  return {
    symbol: "US100",
    resolution: "MINUTE",
    addedAt: 1785578400, // 2026-08-01 10:00 UTC
    latestCandle: 1786113600, // 2026-08-07 14:40 UTC
    collection: "collecting",
    ...over,
  };
}

function instrument(symbol: string): Instrument {
  return {
    symbol,
    name: `${symbol} name`,
    assetClass: "INDICES",
    tradeable: true,
    bid: 1,
    ask: 2,
  };
}

beforeEach(() => {
  fakeArchive = new FakeArchive();
  catalogue = new FakeCatalogue();
});

describe("Archive panel — the list (terminal-data-manager spec)", () => {
  it("shows each pair with how collection is going and how fresh it is", async () => {
    fakeArchive.pairs = [pair()];
    render(<ArchiveView />);

    const row = (await screen.findByText("US100")).closest("tr")!;
    expect(within(row).getByText("MINUTE")).toBeInTheDocument();
    expect(within(row).getByText("collecting")).toBeInTheDocument();
    expect(within(row).getByText("2026-08-07 14:40 UTC")).toBeInTheDocument();
  });

  it("marks a pair that stopped collecting out from the rest", async () => {
    // Being on the list proves nothing: a subscription can die without a sound,
    // and the only symptom is a series that stops growing.
    fakeArchive.pairs = [pair(), pair({ symbol: "GOLD", collection: "stalled" })];
    render(<ArchiveView />);

    await screen.findByText("GOLD");
    expect(screen.getByTestId("pair-US100|MINUTE")).toHaveAttribute("data-stalled", "false");
    expect(screen.getByTestId("pair-GOLD|MINUTE")).toHaveAttribute("data-stalled", "true");
    expect(screen.getByText("stalled")).toBeInTheDocument();
  });

  it("says nothing is archived rather than showing an empty table", async () => {
    render(<ArchiveView />);
    expect(await screen.findByText(/nothing is being archived yet/i)).toBeInTheDocument();
  });

  it("tells an unreachable archive apart from an empty one", async () => {
    // The same empty array either way; only one of them means the operator has
    // nothing set up.
    fakeArchive.listFailure = new MarketDataError(
      "unreachable",
      "the candle archive is not reachable",
    );
    render(<ArchiveView />);

    expect(await screen.findByText(/archive is not reachable/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing is being archived yet/i)).not.toBeInTheDocument();
  });
});

describe("Archive panel — adding a pair", () => {
  async function pick(user: ReturnType<typeof userEvent.setup>, symbol: string) {
    catalogue.results = [instrument(symbol)];
    await user.type(screen.getByLabelText(/find an instrument/i), symbol);
    // Scoped to the results list: a row for the same symbol already on the list
    // carries a button naming it too, and picking that one would stop the pair
    // rather than choose it.
    const results = await screen.findByRole("list");
    await user.click(within(results).getByRole("button", { name: new RegExp(symbol) }));
  }

  it("adds the instrument picked from the search at the chosen resolution", async () => {
    const user = userEvent.setup();
    render(<ArchiveView />);
    await screen.findByText(/nothing is being archived yet/i);

    await pick(user, "US100");
    await user.selectOptions(screen.getByLabelText(/resolution to archive/i), "HOUR");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(fakeArchive.trackCalls).toEqual([{ symbol: "US100", resolution: "HOUR" }]);
    // The list is the claim, not the call: 10.9 is about what the operator sees.
    const row = (await screen.findByText("US100")).closest("tr")!;
    expect(within(row).getByText("HOUR")).toBeInTheDocument();
  });

  it("shows the archive's reason when it refuses, not a generic failure", async () => {
    const user = userEvent.setup();
    fakeArchive.trackFailure = new MarketDataError(
      "refused",
      "20 pairs are already collected; raise MAX_TRACKED_PAIRS to add more",
    );
    render(<ArchiveView />);
    await screen.findByText(/nothing is being archived yet/i);

    await pick(user, "US100");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /raise MAX_TRACKED_PAIRS to add more/i,
    );
  });

  it("says a pair is already archived instead of sending the request again", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    render(<ArchiveView />);
    await screen.findByText("US100");

    await pick(user, "US100");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByText(/already being archived/i)).toBeInTheDocument();
    expect(fakeArchive.trackCalls).toHaveLength(0);
    expect(screen.getAllByTestId(/^pair-/)).toHaveLength(1);
  });
});

describe("Archive panel — stopping a pair", () => {
  it("asks first, promises the candles stay, and drops the row once confirmed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    render(<ArchiveView />);
    await screen.findByText("US100");

    await user.click(screen.getByRole("button", { name: /stop archiving us100 minute/i }));

    // Nothing has happened yet — and the confirmation says what stopping does
    // not cost, because an archive that dropped data on a configuration change
    // would not be an archive.
    expect(fakeArchive.untrackCalls).toHaveLength(0);
    expect(screen.getByText(/candles already collected stay/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^stop collecting$/i }));

    expect(fakeArchive.untrackCalls).toEqual([{ symbol: "US100", resolution: "MINUTE" }]);
    await waitFor(() => expect(screen.queryByTestId("pair-US100|MINUTE")).not.toBeInTheDocument());
  });

  it("leaves the pair collecting when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    render(<ArchiveView />);
    await screen.findByText("US100");

    await user.click(screen.getByRole("button", { name: /stop archiving us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(fakeArchive.untrackCalls).toHaveLength(0);
    expect(screen.getByTestId("pair-US100|MINUTE")).toBeInTheDocument();
  });
});

describe("Archive panel — coverage", () => {
  it("shows how far the archive reaches, and whether that is as far as it can", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    fakeArchive.coverageAnswer = {
      symbol: "US100",
      resolution: "MINUTE",
      ranges: [{ from: 1785542400, to: 1786113600, historyEnded: true }],
      earliestReachable: 1785542400,
    };
    render(<ArchiveView />);

    await user.click(await screen.findByText("US100"));

    const panel = await screen.findByRole("complementary");
    expect(within(panel).getByText(/coverage · us100 minute/i)).toBeInTheDocument();
    expect(within(panel).getByText("2026-08-01 00:00 UTC")).toBeInTheDocument();
    expect(within(panel).getByText("2026-08-07 14:40 UTC")).toBeInTheDocument();
    expect(within(panel).getByText(/end of the provider's history/i)).toBeInTheDocument();
  });

  it("says nothing is verified rather than showing an empty range", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ collection: "never_collected", latestCandle: null })];
    render(<ArchiveView />);

    await user.click(await screen.findByText("US100"));
    expect(await screen.findByText(/nothing verified yet/i)).toBeInTheDocument();
  });
});
