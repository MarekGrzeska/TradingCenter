import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import type {
  AssetClass,
  Instrument,
  JobEstimate,
  PairRequest,
  Resolution,
  TrackedPair,
  TrackPairsResult,
} from "../data/types";

/**
 * The wizard talks to two back ends: the gateway's catalogue (asset classes,
 * instruments) through `instruments`, and the archive's job machinery
 * (estimate, trackPairs) through `archive`. Both are driven by hand here —
 * the acceptance dialog's whole point is showing exactly what a real
 * `estimateJob` would return, so a mock that always answers the same thing
 * would assert nothing about it.
 */
class FakeGateway {
  classes: AssetClass[] = [];
  instrumentsByClass: Instrument[] = [];

  listAssetClasses = async () => this.classes;
  listInstruments = async () => ({
    instruments: this.instrumentsByClass,
    count: this.instrumentsByClass.length,
    truncated: false,
  });
  searchInstruments = async () => [];
}

class FakeArchive {
  estimateAnswer: JobEstimate | null = null;
  estimateFailure: Error | null = null;
  trackAnswer: TrackPairsResult | null = null;
  trackFailure: Error | null = null;
  estimateCalls: Array<{ pairs: PairRequest[]; collectFrom: number }> = [];
  trackCalls: Array<{ pairs: PairRequest[]; collectFrom: number }> = [];

  estimateJob = async (pairs: PairRequest[], collectFrom: number) => {
    this.estimateCalls.push({ pairs, collectFrom });
    if (this.estimateFailure) throw this.estimateFailure;
    return (
      this.estimateAnswer ?? { pairs: [], totalEstimatedCandles: 0, totalEstimatedBytes: 0 }
    );
  };

  trackPairs = async (pairs: PairRequest[], collectFrom: number) => {
    this.trackCalls.push({ pairs, collectFrom });
    if (this.trackFailure) throw this.trackFailure;
    return this.trackAnswer ?? { results: [], jobId: null };
  };
}

let fakeGateway: FakeGateway;
let fakeArchive: FakeArchive;

vi.mock("../data/marketData", () => ({
  get instruments() {
    return fakeGateway;
  },
  get archive() {
    return fakeArchive;
  },
}));

const { AddInstrumentWizard } = await import("./AddInstrumentWizard");

function instrument(symbol: string, assetClass: AssetClass = "CRYPTO"): Instrument {
  return { symbol, name: `${symbol} name`, assetClass, tradeable: true, bid: 1, ask: 2 };
}

function pairEstimate(symbol: string, resolution: Resolution, over: Partial<JobEstimate["pairs"][number]> = {}) {
  return {
    symbol,
    resolution,
    effectiveFrom: 1577836800, // 2020-01-01
    clipped: false,
    estimatedCandles: 1000,
    estimatedBytes: 64000,
    unknown: false,
    ...over,
  };
}

beforeEach(() => {
  fakeGateway = new FakeGateway();
  fakeGateway.classes = ["CRYPTO"];
  fakeGateway.instrumentsByClass = [instrument("BTCUSD")];
  fakeArchive = new FakeArchive();
});

function renderWizard(existingPairs: TrackedPair[] = []) {
  const onCollected = vi.fn();
  render(
    <MemoryRouter>
      <AddInstrumentWizard existingPairs={existingPairs} onCollected={onCollected} />
    </MemoryRouter>,
  );
  return { onCollected };
}

async function pickAssetClass(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("combobox", { name: "Asset class" }));
  await user.click(await screen.findByRole("option", { name }));
}

async function pickInstrument(user: ReturnType<typeof userEvent.setup>, symbol: string) {
  await user.click(screen.getByRole("combobox", { name: "Instrument" }));
  await user.click(await screen.findByRole("option", { name: new RegExp(symbol) }));
}

describe("AddInstrumentWizard — steps (terminal-data-manager spec)", () => {
  it("blocks review until an instrument and at least one resolution are chosen", async () => {
    const user = userEvent.setup();
    renderWizard();

    const submit = screen.getByRole("button", { name: /review and add/i });
    expect(submit).toBeDisabled();
    expect(screen.getByText(/choose an instrument/i)).toBeInTheDocument();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    expect(submit).toBeDisabled();
    expect(screen.getByText(/choose at least one resolution/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "1m" }));
    expect(submit).toBeEnabled();
  });

  it("clears the chosen instrument when the asset class changes", async () => {
    const user = userEvent.setup();
    fakeGateway.classes = ["CRYPTO", "INDICES"];
    renderWizard();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    expect(screen.getByText("BTCUSD")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear Asset class" }));
    await pickAssetClass(user, "INDICES");

    expect(screen.queryByText("BTCUSD")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Instrument" })).toBeInTheDocument();
  });
});

describe("AddInstrumentWizard — the acceptance dialog", () => {
  async function reachDialog(user: ReturnType<typeof userEvent.setup>) {
    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "1m" }));
    await user.click(screen.getByRole("button", { name: "1h" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));
  }

  it("prices every pair, shows the range and a total, and asks for one estimate covering both resolutions", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE"), pairEstimate("BTCUSD", "HOUR")],
      totalEstimatedCandles: 2000,
      totalEstimatedBytes: 128000,
    };
    renderWizard();

    await reachDialog(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("MINUTE")).toBeInTheDocument();
    expect(within(dialog).getByText("HOUR")).toBeInTheDocument();
    expect(within(dialog).getByText(/total: 2,000 candles/i)).toBeInTheDocument();
    expect(fakeArchive.estimateCalls).toHaveLength(1);
    expect(fakeArchive.estimateCalls[0].pairs).toEqual([
      { symbol: "BTCUSD", resolution: "MINUTE" },
      { symbol: "BTCUSD", resolution: "HOUR" },
    ]);
  });

  it("marks a clipped range and a pair already being collected", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE", { clipped: true }), pairEstimate("BTCUSD", "HOUR")],
      totalEstimatedCandles: 2000,
      totalEstimatedBytes: 128000,
    };
    renderWizard([
      {
        symbol: "BTCUSD",
        resolution: "HOUR",
        addedAt: 0,
        collectFrom: 0,
        latestCandle: null,
        collection: "collecting",
      },
    ]);

    await reachDialog(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/clipped/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/already collecting/i)).toBeInTheDocument();
  });

  it("blocks acceptance and adds nothing when the estimate fails", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateFailure = new Error("archive unreachable");
    renderWizard();

    await reachDialog(user);

    expect(await screen.findByText(/could not price this job/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start collecting/i })).toBeDisabled();
    expect(fakeArchive.trackCalls).toHaveLength(0);
  });

  it("adds nothing and keeps the wizard's choices when the dialog is dismissed", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE")],
      totalEstimatedCandles: 1000,
      totalEstimatedBytes: 64000,
    };
    renderWizard();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "1m" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));

    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(fakeArchive.trackCalls).toHaveLength(0);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // The wizard's own choices survived the round trip.
    expect(screen.getByText("BTCUSD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1m", pressed: true })).toBeInTheDocument();
  });

  it("starts collection, lists what is now archiving, points to Data History, and resets the wizard", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE")],
      totalEstimatedCandles: 1000,
      totalEstimatedBytes: 64000,
    };
    fakeArchive.trackAnswer = {
      results: [
        {
          symbol: "BTCUSD",
          resolution: "MINUTE",
          pair: {
            symbol: "BTCUSD",
            resolution: "MINUTE",
            addedAt: 0,
            collectFrom: 0,
            latestCandle: null,
            collection: "never_collected",
          },
          refused: null,
        },
      ],
      jobId: 42,
    };
    const { onCollected } = renderWizard();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "1m" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByText(/collecting started/i)).toBeInTheDocument();
    expect(screen.getByText("BTCUSD MINUTE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /data history/i })).toHaveAttribute(
      "href",
      "/data-history",
    );

    await user.click(screen.getByRole("button", { name: /^done$/i }));

    expect(onCollected).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Back to a clean slate for the next instrument.
    expect(screen.queryByText("BTCUSD")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /review and add/i })).toBeDisabled();
  });

  it("shows a refusal without hiding the pairs that were accepted", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE"), pairEstimate("BTCUSD", "HOUR")],
      totalEstimatedCandles: 2000,
      totalEstimatedBytes: 128000,
    };
    fakeArchive.trackAnswer = {
      results: [
        {
          symbol: "BTCUSD",
          resolution: "MINUTE",
          pair: {
            symbol: "BTCUSD",
            resolution: "MINUTE",
            addedAt: 0,
            collectFrom: 0,
            latestCandle: null,
            collection: "never_collected",
          },
          refused: null,
        },
        {
          symbol: "BTCUSD",
          resolution: "HOUR",
          pair: null,
          refused: "20 pairs are already collected; raise MAX_TRACKED_PAIRS to add more",
        },
      ],
      jobId: 7,
    };
    renderWizard();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "1m" }));
    await user.click(screen.getByRole("button", { name: "1h" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByText("BTCUSD MINUTE")).toBeInTheDocument();
    expect(screen.getByText(/raise MAX_TRACKED_PAIRS/i)).toBeInTheDocument();
  });
});
