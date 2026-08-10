import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
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
    candleCount: 12431,
    estimatedBytes: 1193376,
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
    expect(within(row).getByText("m1")).toBeInTheDocument();
    expect(within(row).getByText("h1")).toBeInTheDocument();
    expect(within(row).getByText("day")).toBeInTheDocument();
    expect(within(row).getByText("week")).toBeInTheDocument();
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
    expect(within(row).getByText("m1").className).not.toBe(within(row).getByText("h1").className);
  });

  it("does not mark an instrument whose resolutions are all healthy", async () => {
    fakeArchive.pairs = [pair({ resolution: "MINUTE", collection: "collecting" })];
    renderView();

    const row = await screen.findByTestId("instrument-US100");
    expect(row).toHaveAttribute("data-stalled", "false");
  });
});

describe("Instruments list — volume per interval, on expand", () => {
  it("shows how many candles are collected, roughly how much they take, and since when", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({
        resolution: "MINUTE",
        candleCount: 12431,
        estimatedBytes: 1193376,
        earliestCandle: 1785542400, // 2026-08-01
      }),
    ];
    renderView();

    await user.click(await screen.findByText("US100"));

    expect(await screen.findByText(/12,431 candles/)).toBeInTheDocument();
    expect(screen.getByText(/1\.1 MB/)).toBeInTheDocument();
    expect(screen.getByText(/2026-08-01/)).toBeInTheDocument();
  });

  it("names an interval that has collected nothing, rather than showing a zero", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({
        resolution: "MINUTE",
        candleCount: 0,
        estimatedBytes: 0,
        earliestCandle: null,
        latestCandle: null,
        collection: "never_collected",
      }),
    ];
    renderView();

    await user.click(await screen.findByText("US100"));

    expect(await screen.findByText(/nothing collected yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/0 candles/)).not.toBeInTheDocument();
  });

  it("gives each interval its own since, when they reach back different distances", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [
      pair({ resolution: "MINUTE", earliestCandle: 1785542400 }), // 2026-08-01
      pair({ resolution: "DAY", earliestCandle: 1577923200 }), // 2020-01-02
    ];
    renderView();

    await user.click(await screen.findByText("US100"));

    expect(await screen.findByText(/2026-08-01/)).toBeInTheDocument();
    expect(screen.getByText(/2020-01-02/)).toBeInTheDocument();
  });
});

describe("Instruments list — coverage gaps, on expand", () => {
  it("says nothing about coverage when it is one continuous range", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    let coverageRequested: () => void;
    const requested = new Promise<void>((resolve) => {
      coverageRequested = resolve;
    });
    fakeArchive.coverage = async (symbol: string, resolution: Resolution) => {
      coverageRequested();
      return {
        symbol,
        resolution,
        ranges: [{ from: 1785542400, to: 1786113600, historyEnded: true }],
        earliestReachable: 1785542400,
      };
    };
    renderView();

    await user.click(await screen.findByText("US100"));
    await requested;
    // One continuous range still has to reach the component and be applied
    // before its absence from the screen means anything.
    await act(async () => {});

    expect(screen.queryByText(/stretches/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/covered from/i)).not.toBeInTheDocument();
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
    expect(
      await screen.findByText(/coverage has gaps — 2 stretches, not one continuous range/i),
    ).toBeInTheDocument();
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
    // A modal, the same weight of decision as the wizard's own acceptance dialog.
    const dialog = screen.getByRole("dialog", { name: /delete us100/i });
    expect(within(dialog).getByText(/it cannot be undone/i)).toBeInTheDocument();
    // The old assurance no longer holds — deleting removes the data.
    expect(screen.queryByText(/candles already collected stay/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^delete data$/i }));

    expect(fakeArchive.deleteCalls).toEqual([{ symbol: "US100", resolution: "MINUTE" }]);
    await waitFor(() => {
      const row = screen.getByTestId("instrument-US100");
      expect(within(row).queryByText("m1")).not.toBeInTheDocument();
      expect(within(row).getByText("h1")).toBeInTheDocument();
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
    expect(within(screen.getByTestId("instrument-US100")).getByText("m1")).toBeInTheDocument();
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

    const dialog = screen.getByRole("dialog", { name: /delete us100/i });
    expect(dialog).toHaveTextContent("MINUTE");
    expect(dialog).toHaveTextContent("HOUR");
    expect(dialog).toHaveTextContent(/cannot be undone/i);
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
      expect(within(row).queryByText("m1")).not.toBeInTheDocument();
      expect(within(row).getByText("h1")).toBeInTheDocument();
    });
    expect(screen.getByText(/could not delete HOUR/i)).toBeInTheDocument();
  });

  it("asks in a dialog, the same way starting collection does", async () => {
    const user = userEvent.setup();
    fakeArchive.pairs = [pair()];
    renderView();

    await screen.findByText("US100");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete US100" }));

    const dialog = screen.getByRole("dialog", { name: /delete us100/i });
    // Says what goes, how far back it reached, and that collection stops with it.
    expect(dialog).toHaveTextContent(/permanently removes/i);
    expect(dialog).toHaveTextContent(/2026-08-01/);
    expect(dialog).toHaveTextContent(/collecting stops/i);

    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fakeArchive.deleteCalls).toHaveLength(0);
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
