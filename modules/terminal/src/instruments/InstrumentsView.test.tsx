import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
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
  deleteCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  /** Set to make one particular pair's deletion reject, the way a real
   *  archive would for one interval while the rest of a whole-instrument
   *  delete succeeds. */
  deleteFailures = new Set<string>();

  listPairs = async () => {
    if (this.listFailure) throw this.listFailure;
    return [...this.pairs];
  };

  deletePair = async (symbol: string, resolution: Resolution) => {
    this.deleteCalls.push({ symbol, resolution });
    if (this.deleteFailures.has(`${symbol}|${resolution}`)) {
      throw new Error(`could not delete ${symbol} ${resolution}`);
    }
    const removed = this.pairs.find(
      (pair) => pair.symbol === symbol && pair.resolution === resolution,
    );
    this.pairs = this.pairs.filter(
      (pair) => !(pair.symbol === symbol && pair.resolution === resolution),
    );
    return {
      symbol,
      resolution,
      deletedAt: 1786269600,
      candlesRemoved: removed?.latestCandle === null ? 0 : 3,
      removedFrom: removed?.earliestCandle ?? null,
      removedTo: removed?.latestCandle ?? null,
    };
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
    earliestCandle: 1785542400, // 2026-08-01 00:00 UTC
    latestCandle: 1786113600, // 2026-08-07 14:40 UTC
    collection: "collecting",
    ...over,
  };
}

beforeEach(() => {
  fakeArchive = new FakeArchive();
});

// A successful delete renders a banner linking to `/data-history`, which
// needs a router beneath it even in tests that never click Delete.
function renderView() {
  return render(
    <MemoryRouter>
      <InstrumentsView />
    </MemoryRouter>,
  );
}

describe("Instruments list — grouping (terminal-data-manager spec)", () => {
  it("puts every resolution of the same instrument in one row, abbreviated", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE" }),
      pair({ resolution: "HOUR" }),
      pair({ resolution: "DAY" }),
      pair({ resolution: "WEEK" }),
    ];
    renderView();

    expect(await screen.findAllByText("US100")).toHaveLength(1);
    const row = screen.getByTestId("instrument-US100");
    expect(within(row).getByText("1m")).toBeInTheDocument();
    expect(within(row).getByText("1h")).toBeInTheDocument();
    expect(within(row).getByText("1D")).toBeInTheDocument();
    expect(within(row).getByText("1W")).toBeInTheDocument();
  });

  it("says since when there is data with one date when every resolution agrees", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", earliestCandle: 1785542400 }), // 2026-08-01
      pair({ resolution: "HOUR", earliestCandle: 1785542400 }),
    ];
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    // One date, said once — not the same date repeated per resolution.
    expect(within(row).getAllByText(/2026-08-01/)).toHaveLength(1);
  });

  it("splits the date per resolution when they do not reach equally far back", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", earliestCandle: 1785542400 }), // 2026-08-01
      pair({ resolution: "MINUTE_5", earliestCandle: 1785542400 }),
      pair({ resolution: "DAY", earliestCandle: 1577923200 }), // 2020-01-02
    ];
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    const deepest = within(row).getByText(/2020-01-02/).closest("div");
    // Which resolutions the deeper history belongs to has to be readable off
    // the row; a bare pair of dates says nothing about which is which.
    expect(deepest).toHaveTextContent("1D");
    expect(within(row).getByText(/2026-08-01/).closest("div")).toHaveTextContent("1m · 5m");
  });

  it("says a resolution has nothing yet rather than leaving its date blank", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", earliestCandle: null, collection: "never_collected" }),
      pair({ resolution: "DAY", earliestCandle: 1577923200 }), // 2020-01-02
    ];
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    expect(within(row).getByText("nothing yet").closest("div")).toHaveTextContent("1m");
  });

  it("says nothing yet for an instrument that has collected nothing at all", async () => {
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", earliestCandle: null, collection: "never_collected" }),
      pair({ resolution: "DAY", earliestCandle: null, collection: "never_collected" }),
    ];
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    expect(within(row).getByText("nothing yet")).toBeInTheDocument();
  });

  it("says nothing is archived rather than showing an empty table", async () => {
    renderView();
    expect(await screen.findByText(/nothing is being archived yet/i)).toBeInTheDocument();
  });

  it("tells an unreachable archive apart from an empty one", async () => {
    fakeArchive.listFailure = new MarketDataError(
      "unreachable",
      "the candle archive is not reachable",
    );
    renderView();

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
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    expect(row).toHaveAttribute("data-stalled", "true");
    // The healthy resolution and the stalled one must not read the same way.
    expect(within(row).getByText("1m").className).not.toBe(within(row).getByText("1h").className);
  });

  it("does not mark an instrument whose resolutions are all healthy", async () => {
    fakeArchive.pairs = [pair({ resolution: "MINUTE", collection: "collecting" })];
    renderView();

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
    renderView();

    await user.click(await screen.findByText("US100"));

    expect(await screen.findAllByText(/covered from/i)).toHaveLength(2);
    expect(screen.getAllByText(/end of the provider's history/i)).toHaveLength(2);
  });

  // How fresh the data is, per interval — the question a row's collection state answers
  // qualitatively and this answers exactly (terminal-data-manager spec, "Świeżość
  // danych").
  it("gives the newest collected candle for each interval", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", latestCandle: 1786113600 }), // 2026-08-07 14:40 UTC
      pair({ resolution: "HOUR", latestCandle: null }),
    ];
    renderView();

    await user.click(await screen.findByText("US100"));

    expect(await screen.findByText(/newest: 2026-08-07 14:40 UTC/)).toBeInTheDocument();
    // Nothing collected yet is a dash, never a zero or a fabricated instant.
    expect(screen.getByText(/newest: —/)).toBeInTheDocument();
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
    renderView();

    await user.click(await screen.findByText("US100"));
    expect(await screen.findByText(/in 2 stretches, with gaps between them/i)).toBeInTheDocument();
  });

  it("says nothing is verified rather than showing an empty range", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ collection: "never_collected", latestCandle: null })];
    renderView();

    await user.click(await screen.findByText("US100"));
    expect(await screen.findByText(/nothing verified yet for this interval/i)).toBeInTheDocument();
  });
});

describe("Instruments list — deleting a single interval", () => {
  it("asks first, warns the removal is permanent, and drops only that interval", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE" }), pair({ resolution: "HOUR" })];
    renderView();

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /delete us100 minute/i }));

    expect(fakeArchive.deleteCalls).toHaveLength(0);
    expect(screen.getByText(/this cannot be undone/i)).toBeInTheDocument();
    // The old assurance no longer holds — deleting removes the data.
    expect(screen.queryByText(/candles already collected stay/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    expect(fakeArchive.deleteCalls).toEqual([{ symbol: "US100", resolution: "MINUTE" }]);
    await waitFor(() => {
      const row = screen.getByTestId("instrument-US100");
      expect(within(row).queryByText("1m")).not.toBeInTheDocument();
      expect(within(row).getByText("1h")).toBeInTheDocument();
    });
  });

  it("leaves the interval collecting when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    renderView();

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /delete us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(fakeArchive.deleteCalls).toHaveLength(0);
    expect(screen.getByTestId("instrument-US100")).toBeInTheDocument();
  });

  it("reports how many candles were removed and points to Data History", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE", latestCandle: 1786113600 })];
    renderView();

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /delete us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    expect(await screen.findByText(/deleted 3 candles for US100 in MINUTE/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /data history/i })).toHaveAttribute(
      "href",
      "/data-history",
    );
  });

  it("says so and leaves the interval listed when deletion fails", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    fakeArchive.deleteFailures.add("US100|MINUTE");
    renderView();

    await user.click(await screen.findByText("US100"));
    await user.click(screen.getByRole("button", { name: /delete us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    expect(await screen.findByText(/could not delete/i)).toBeInTheDocument();
    expect(within(screen.getByTestId("instrument-US100")).getByText("1m")).toBeInTheDocument();
  });
});

describe("Instruments list — deleting a whole instrument", () => {
  it("names every resolution that will be deleted, and removes the whole row once confirmed", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE" }),
      pair({ resolution: "HOUR" }),
      pair({ symbol: "GOLD", resolution: "DAY" }),
    ];
    renderView();

    await screen.findByText("US100");
    await user.click(screen.getByRole("button", { name: "Delete US100" }));

    const confirmation = screen.getByText(/delete us100 in/i);
    expect(confirmation).toHaveTextContent("MINUTE");
    expect(confirmation).toHaveTextContent("HOUR");
    expect(confirmation).toHaveTextContent(/cannot be undone/i);
    expect(fakeArchive.deleteCalls).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    expect(fakeArchive.deleteCalls).toEqual(
      expect.arrayContaining([
        { symbol: "US100", resolution: "MINUTE" },
        { symbol: "US100", resolution: "HOUR" },
      ]),
    );
    await waitFor(() => expect(screen.queryByTestId("instrument-US100")).not.toBeInTheDocument());
    // The other instrument is unrelated and stays exactly where it was.
    expect(screen.getByTestId("instrument-GOLD")).toBeInTheDocument();
  });

  it("reports the total removed across every interval that succeeded", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE" }), pair({ resolution: "HOUR" })];
    renderView();

    await screen.findByText("US100");
    await user.click(screen.getByRole("button", { name: "Delete US100" }));
    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    // Both pairs share the fake's fixed 3-candle answer, so two intervals sum to 6.
    expect(await screen.findByText(/deleted 6 candles for US100 in MINUTE, HOUR/i)).toBeInTheDocument();
  });

  it("drops what succeeded, keeps what failed listed, and names it in the confirmation", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair({ resolution: "MINUTE" }), pair({ resolution: "HOUR" })];
    fakeArchive.deleteFailures.add("US100|HOUR");
    renderView();

    await screen.findByText("US100");
    await user.click(screen.getByRole("button", { name: "Delete US100" }));
    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    await waitFor(() => {
      const row = screen.getByTestId("instrument-US100");
      expect(within(row).queryByText("1m")).not.toBeInTheDocument();
      expect(within(row).getByText("1h")).toBeInTheDocument();
    });
    expect(screen.getByText(/could not delete HOUR/i)).toBeInTheDocument();
  });

  it("dismisses the deletion banner on request", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    renderView();

    await screen.findByText("US100");
    await user.click(screen.getByRole("button", { name: "Delete US100" }));
    await user.click(screen.getByRole("button", { name: /^delete data$/i }));
    await screen.findByText(/deleted 3 candles/i);

    await user.click(screen.getByRole("button", { name: /dismiss/i }));

    expect(screen.queryByText(/deleted 3 candles/i)).not.toBeInTheDocument();
  });
});
