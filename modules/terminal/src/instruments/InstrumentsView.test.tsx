import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MarketDataError } from "../data/types";
import type { PairCoverage, Resolution, TrackedPair } from "../data/types";

/**
 * A stand-in archive the test drives — the list changes as the panel acts on
 * it, the same way `market-data` would.
 */
class FakeArchive {
  pairs: TrackedPair[] = [];
  coverageAnswer: PairCoverage | null = null;
  listFailure: Error | null = null;
  untrackCalls: Array<{ symbol: string; resolution: Resolution }> = [];

  listPairs = async () => {
    if (this.listFailure) throw this.listFailure;
    return [...this.pairs];
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

/** The wizard's own picker source — a fixed, empty catalogue is enough here:
 *  these tests are about the list, not about adding an instrument. */
const fakeGateway = {
  listAssetClasses: async () => [],
  listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
  searchInstruments: async () => [],
};

let fakeArchive: FakeArchive;

vi.mock("../data/marketData", () => ({
  // A getter, so each test's freshly built double is the one the view reads.
  get archive() {
    return fakeArchive;
  },
  instruments: fakeGateway,
}));

const { InstrumentsView } = await import("./InstrumentsView");

function pair(over: Partial<TrackedPair> = {}): TrackedPair {
  return {
    symbol: "US100",
    resolution: "MINUTE",
    addedAt: 1785578400, // 2026-08-01 10:00 UTC
    collectFrom: 1785578400,
    latestCandle: 1786113600, // 2026-08-07 14:40 UTC
    collection: "collecting",
    ...over,
  };
}

beforeEach(() => {
  fakeArchive = new FakeArchive();
});

describe("Instruments list — grouping (terminal-data-manager spec)", () => {
  it("puts every resolution of the same instrument in one row, abbreviated", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE" }),
      pair({ resolution: "HOUR" }),
      pair({ resolution: "DAY" }),
      pair({ resolution: "WEEK" }),
    ];
    render(<InstrumentsView />);

    expect(await screen.findAllByText("US100")).toHaveLength(1);
    const row = screen.getByTestId("instrument-US100");
    expect(within(row).getByText("1m")).toBeInTheDocument();
    expect(within(row).getByText("1h")).toBeInTheDocument();
    expect(within(row).getByText("1D")).toBeInTheDocument();
    expect(within(row).getByText("1W")).toBeInTheDocument();
  });

  it("shows the earliest addition among its resolutions as when archiving began", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", addedAt: 1785578400 }), // 2026-08-01
      pair({ resolution: "HOUR", addedAt: 1780000000 }), // earlier
    ];
    render(<InstrumentsView />);

    const row = await screen.findByTestId("instrument-US100");
    expect(within(row).getByText(/2026-05-28/)).toBeInTheDocument();
  });

  it("says nothing is archived rather than showing an empty table", async () => {
    render(<InstrumentsView />);
    expect(await screen.findByText(/nothing is being archived yet/i)).toBeInTheDocument();
  });

  it("tells an unreachable archive apart from an empty one", async () => {
    fakeArchive.listFailure = new MarketDataError(
      "unreachable",
      "the candle archive is not reachable",
    );
    render(<InstrumentsView />);

    expect(await screen.findByText(/archive is not reachable/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing is being archived yet/i)).not.toBeInTheDocument();
  });
});

describe("Instruments list — a lagging interval", () => {
  it("marks the row and the stalled interval out from the rest", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", collection: "collecting" }),
      pair({ resolution: "HOUR", collection: "stalled" }),
    ];
    render(<InstrumentsView />);

    const row = await screen.findByTestId("instrument-US100");
    expect(row).toHaveAttribute("data-stalled", "true");
    // The healthy resolution and the stalled one must not read the same way.
    expect(within(row).getByText("1m").className).not.toBe(within(row).getByText("1h").className);
  });

  it("does not mark an instrument whose resolutions are all healthy", async () => {
    fakeArchive.pairs = [pair({ resolution: "MINUTE", collection: "collecting" })];
    render(<InstrumentsView />);

    const row = await screen.findByTestId("instrument-US100");
    expect(row).toHaveAttribute("data-stalled", "false");
  });
});

describe("Instruments list — coverage on expand", () => {
  it("shows coverage for every resolution once the row is expanded", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE" }), pair({ resolution: "HOUR" })];
    fakeArchive.coverageAnswer = {
      symbol: "US100",
      resolution: "MINUTE",
      ranges: [{ from: 1785542400, to: 1786113600, historyEnded: true }],
      earliestReachable: 1785542400,
    };
    render(<InstrumentsView />);

    await user.click(await screen.findByText("US100"));

    expect(await screen.findAllByText(/covered from/i)).toHaveLength(2);
    expect(screen.getAllByText(/end of the provider's history/i)).toHaveLength(2);
  });

  it("names the gaps when coverage is more than one stretch", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    fakeArchive.coverageAnswer = {
      symbol: "US100",
      resolution: "MINUTE",
      ranges: [
        { from: 1785542400, to: 1785600000, historyEnded: false },
        { from: 1785700000, to: 1786113600, historyEnded: false },
      ],
      earliestReachable: null,
    };
    render(<InstrumentsView />);

    await user.click(await screen.findByText("US100"));
    expect(await screen.findByText(/in 2 stretches, with gaps between them/i)).toBeInTheDocument();
  });

  it("says nothing is verified rather than showing an empty range", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ collection: "never_collected", latestCandle: null })];
    render(<InstrumentsView />);

    await user.click(await screen.findByText("US100"));
    expect(await screen.findByText(/nothing verified yet for this interval/i)).toBeInTheDocument();
  });
});

describe("Instruments list — removing a single interval", () => {
  it("asks first, promises the candles stay, and drops only that interval", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE" }), pair({ resolution: "HOUR" })];
    render(<InstrumentsView />);

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /stop archiving us100 minute/i }));

    expect(fakeArchive.untrackCalls).toHaveLength(0);
    expect(screen.getByText(/candles already collected stay/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^stop collecting$/i }));

    expect(fakeArchive.untrackCalls).toEqual([{ symbol: "US100", resolution: "MINUTE" }]);
    await waitFor(() => {
      const row = screen.getByTestId("instrument-US100");
      expect(within(row).queryByText("1m")).not.toBeInTheDocument();
      expect(within(row).getByText("1h")).toBeInTheDocument();
    });
  });

  it("leaves the interval collecting when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    render(<InstrumentsView />);

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /stop archiving us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(fakeArchive.untrackCalls).toHaveLength(0);
    expect(screen.getByTestId("instrument-US100")).toBeInTheDocument();
  });
});

describe("Instruments list — removing a whole instrument", () => {
  it("names every resolution that will stop, and removes the whole row once confirmed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE" }),
      pair({ resolution: "HOUR" }),
      pair({ symbol: "GOLD", resolution: "DAY" }),
    ];
    render(<InstrumentsView />);

    await screen.findByText("US100");
    await user.click(screen.getByRole("button", { name: "Stop archiving US100" }));

    const confirmation = screen.getByText(/stop archiving us100 in/i);
    expect(confirmation).toHaveTextContent("MINUTE");
    expect(confirmation).toHaveTextContent("HOUR");
    expect(fakeArchive.untrackCalls).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /^stop collecting$/i }));

    expect(fakeArchive.untrackCalls).toEqual(
      expect.arrayContaining([
        { symbol: "US100", resolution: "MINUTE" },
        { symbol: "US100", resolution: "HOUR" },
      ]),
    );
    await waitFor(() => expect(screen.queryByTestId("instrument-US100")).not.toBeInTheDocument());
    // The other instrument is unrelated and stays exactly where it was.
    expect(screen.getByTestId("instrument-GOLD")).toBeInTheDocument();
  });
});
