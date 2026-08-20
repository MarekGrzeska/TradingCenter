import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { todayInWarsaw, warsawMidnightEpochSeconds } from "../ui/formatTime";
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
  truncated = false;

  listAssetClasses = async () => this.classes;
  listInstruments = async () => ({
    instruments: this.instrumentsByClass,
    count: this.instrumentsByClass.length,
    truncated: this.truncated,
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

function trackedPair(resolution: Resolution): TrackedPair {
  return {
    symbol: "BTCUSD",
    resolution,
    addedAt: 0,
    collectFrom: 0,
    earliestCandle: null,
    latestCandle: null,
    collection: "never_collected",
    candleCount: 0,
    estimatedBytes: 0,
  };
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

    await user.click(screen.getByRole("button", { name: "m1" }));
    expect(submit).toBeEnabled();
  });

  // The date field is the operator's own calendar, not UTC's — picking "2026-08-01" MUST
  // mean the start of that day in Warsaw (`terminal-shell` spec, "Czas jest pokazywany w
  // polskiej strefie czasowej", scenario "Data podana przez operatora"). And it starts at
  // the beginning of the current year rather than at everything the provider has: an
  // arbitrarily early default would commit every operator to hundreds of requests.
  it("defaults to this Warsaw year and reads the picked date as Warsaw midnight, not UTC", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE")],
      totalEstimatedCandles: 1000,
      totalEstimatedBytes: 64000,
    };
    renderWizard();

    const field = screen.getByLabelText("History from") as HTMLInputElement;
    expect(field.value).toBe(`${todayInWarsaw().slice(0, 4)}-01-01`);
    expect(field.value <= todayInWarsaw()).toBe(true);

    fireEvent.change(field, { target: { value: "2026-08-01" } });
    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "m1" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));

    await screen.findByRole("dialog");
    expect(fakeArchive.estimateCalls[0].collectFrom).toBe(
      warsawMidnightEpochSeconds("2026-08-01"),
    );
  });
});

describe("AddInstrumentWizard — the acceptance dialog", () => {
  async function reachDialog(user: ReturnType<typeof userEvent.setup>) {
    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "m1" }));
    await user.click(screen.getByRole("button", { name: "h1" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));
  }

  it("prices every pair, says the numbers are estimates, and asks once for both resolutions", async () => {
    // The operator decides on cost from these numbers, so their being calendar-period
    // overestimates is part of what the dialog has to say (market-data-jobs spec,
    // "Szacunek jest opisany jako szacunek").
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE"), pairEstimate("BTCUSD", "HOUR")],
      totalEstimatedCandles: 2000,
      totalEstimatedBytes: 128000,
    };
    renderWizard();

    await reachDialog(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/total: 2,000 candles/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/these are estimates/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/market closed for part of the range/i)).toBeInTheDocument();
    expect(fakeArchive.estimateCalls).toHaveLength(1);
    expect(fakeArchive.estimateCalls[0].pairs).toEqual([
      { symbol: "BTCUSD", resolution: "MINUTE" },
      { symbol: "BTCUSD", resolution: "HOUR" },
    ]);
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

  it("starts collection, lists what is now archiving, points to Data History, and resets the wizard", async () => {
    const user = userEvent.setup();
    fakeArchive.estimateAnswer = {
      pairs: [pairEstimate("BTCUSD", "MINUTE")],
      totalEstimatedCandles: 1000,
      totalEstimatedBytes: 64000,
    };
    fakeArchive.trackAnswer = {
      results: [
        { symbol: "BTCUSD", resolution: "MINUTE", pair: trackedPair("MINUTE"), refused: null },
      ],
      jobId: 42,
    };
    const { onCollected } = renderWizard();

    await pickAssetClass(user, "CRYPTO");
    await pickInstrument(user, "BTCUSD");
    await user.click(screen.getByRole("button", { name: "m1" }));
    await user.click(screen.getByRole("button", { name: /review and add/i }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByText(/collecting started/i)).toBeInTheDocument();
    expect(screen.getByText("BTCUSD m1")).toBeInTheDocument();
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
        { symbol: "BTCUSD", resolution: "MINUTE", pair: trackedPair("MINUTE"), refused: null },
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

    await reachDialog(user);
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /start collecting/i }));

    expect(await screen.findByText("BTCUSD m1")).toBeInTheDocument();
    expect(screen.getByText(/raise MAX_TRACKED_PAIRS/i)).toBeInTheDocument();
  });
});
