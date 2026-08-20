import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { MarketDataError } from "../data/types";
import type { Chunk, JobPairView, PairDeletion } from "../data/types";

/** A stand-in archive the test drives — `listJobs` and `listDeletions`
 *  answers change between polls, the same way a real one would while a job
 *  runs or an operator deletes something. */
class FakeArchive {
  rows: JobPairView[] = [];
  deletions: PairDeletion[] = [];
  listFailure: Error | null = null;
  retryFailure: Error | null = null;
  deleteFailure: Error | null = null;
  listCalls = 0;
  retryCalls: number[] = [];
  deleteCalls: number[] = [];

  listJobs = async () => {
    this.listCalls++;
    if (this.listFailure) throw this.listFailure;
    return [...this.rows];
  };

  listDeletions = async () => {
    if (this.listFailure) throw this.listFailure;
    return [...this.deletions];
  };

  retryJob = async (jobId: number) => {
    this.retryCalls.push(jobId);
    if (this.retryFailure) throw this.retryFailure;
    // The view never reads the returned Job — it always reloads from
    // `listJobs` afterwards, so a minimal stand-in is enough here.
    return { id: jobId, createdAt: 0, requestedFrom: 0, attempt: 2, status: "running", chunksDone: 0, chunksTotal: 0, candlesWritten: 0, lastActivityAt: 0, runningPair: null, chunks: [] };
  };

  deleteJob = async (jobId: number) => {
    this.deleteCalls.push(jobId);
    if (this.deleteFailure) throw this.deleteFailure;
    // What the archive does: the entry goes, the candles it collected do not.
    this.rows = this.rows.filter((row) => row.jobId !== jobId);
  };
}

let fakeArchive: FakeArchive;

vi.mock("../data/marketData", () => ({
  get archive() {
    return fakeArchive;
  },
}));

const { CollectionHistoryView } = await import("./CollectionHistoryView");

function chunk(over: Partial<Chunk> = {}): Chunk {
  return {
    id: 1,
    symbol: "US100",
    resolution: "MINUTE",
    chunkStart: 1785542400,
    chunkEnd: 1785600000,
    state: "done",
    attempt: 1,
    candlesWritten: 1000,
    requests: 1,
    failure: null,
    startedAt: 1785542400,
    finishedAt: 1785542500,
    ...over,
  };
}

function row(over: Partial<JobPairView> = {}): JobPairView {
  return {
    jobId: 1,
    symbol: "US100",
    resolution: "MINUTE",
    createdAt: 1785542000,
    requestedFrom: 1785542000,
    attempt: 1,
    status: "succeeded",
    chunksDone: 1,
    chunksTotal: 1,
    candlesWritten: 1000,
    lastActivityAt: 1785542500,
    chunks: [chunk()],
    ...over,
  };
}

function deletion(over: Partial<PairDeletion> = {}): PairDeletion {
  return {
    symbol: "US100",
    resolution: "MINUTE",
    deletedAt: 1786200000,
    candlesRemoved: 250,
    removedFrom: 1785542400,
    removedTo: 1786113600,
    ...over,
  };
}

function renderView() {
  return render(
    <MemoryRouter>
      <CollectionHistoryView />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  fakeArchive = new FakeArchive();
});

afterEach(() => {
  vi.useRealTimers();
});


describe("CollectionHistoryView — rows (terminal-collection-history spec)", () => {
  it("shows a measured share of chunks done and candles written so far for a running job", async () => {
    fakeArchive.rows = [
      row({
        status: "running",
        chunksDone: 2,
        chunksTotal: 8,
        candlesWritten: 4000,
        chunks: [chunk({ state: "done" }), chunk({ id: 2, state: "pending" })],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText("US100")).toBeInTheDocument();
    expect(within(r).getByText(/25% \(2\/8 chunks\)/)).toBeInTheDocument();
    expect(within(r).getByText(/4,000 candles so far/)).toBeInTheDocument();
  });

  it("says nothing was reachable when every chunk was skipped", async () => {
    fakeArchive.rows = [
      row({ candlesWritten: 0, chunksDone: 1, chunksTotal: 1, chunks: [chunk({ state: "skipped" })] }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText(/nothing in this range to collect/)).toBeInTheDocument();
  });

  it("does not turn a failed job into a claim about the provider's history", async () => {
    // A chunk that failed says nothing about what is down there. Counting its absence as
    // "collected nothing" reads an outage as the instrument having no history.
    fakeArchive.rows = [
      row({
        status: "failed",
        candlesWritten: 0,
        chunksDone: 0,
        chunksTotal: 1,
        chunks: [chunk({ state: "failed", failure: "gateway did not answer" })],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByText(/nothing in this range to collect/)).not.toBeInTheDocument();
  });

  it("marks partial coverage as its own state, and lists the failure reasons", async () => {
    fakeArchive.rows = [
      row({
        status: "partial",
        chunksDone: 1,
        chunksTotal: 2,
        chunks: [chunk({ state: "done" }), chunk({ id: 2, state: "failed", failure: "gateway refused" })],
      }),
    ];
    renderView();

    expect(await screen.findByText("partial")).toHaveClass("text-warning");
    expect(screen.getByText("gateway refused")).toBeInTheDocument();
  });
});

describe("CollectionHistoryView — deletions (delete-archived-pair-data)", () => {
  it("names the pair, when, how many candles, and the range they covered", async () => {
    fakeArchive.deletions = [deletion({ candlesRemoved: 42 })];
    renderView();

    const r = await screen.findByTestId("deletion-US100-MINUTE-1786200000");
    expect(within(r).getByText("US100")).toBeInTheDocument();
    expect(within(r).getByText(/−42 candles/)).toBeInTheDocument();
    // A deletion is neither a success nor a failure, and counts as history on its own.
    const label = within(r).getByText("deleted");
    expect(label).not.toHaveClass("text-good");
    expect(label).not.toHaveClass("text-critical");
    expect(screen.queryByText(/nothing has been collected yet/i)).not.toBeInTheDocument();
  });

  it("shows a null range as a dash rather than a fabricated one", async () => {
    fakeArchive.deletions = [deletion({ candlesRemoved: 0, removedFrom: null, removedTo: null })];
    renderView();

    const r = await screen.findByTestId("deletion-US100-MINUTE-1786200000");
    expect(within(r).getByText("—")).toBeInTheDocument();
  });
});

describe("CollectionHistoryView — the job dialog and retry", () => {
  it("opens the whole job from one pair's row, including pairs the row does not show", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ symbol: "US100", resolution: "MINUTE" }),
      row({ symbol: "GOLD", resolution: "HOUR", candlesWritten: 500 }),
    ];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("GOLD")).toBeInTheDocument();
    expect(within(dialog).getByText(/2 pairs/i)).toBeInTheDocument();
  });

  it("says what the retry covers before doing it, and moves the rows to running once queued", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({
        status: "failed",
        chunksDone: 0,
        chunksTotal: 1,
        chunks: [chunk({ state: "failed", failure: "gateway refused" })],
      }),
    ];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));

    const dialog = await screen.findByRole("dialog");
    // The scope, spelled out: this is the job, not the row it was opened from.
    expect(within(dialog).getByText(/re-runs 1 failed chunk across 1 pair/i)).toBeInTheDocument();
    expect(fakeArchive.retryCalls).toHaveLength(0);

    fakeArchive.rows = [row({ status: "running", chunksDone: 0, chunksTotal: 1 })];
    await user.click(screen.getByRole("button", { name: /retry job/i }));

    expect(fakeArchive.retryCalls).toEqual([1]);
    await waitFor(() => expect(screen.getByText("running")).toBeInTheDocument());
  });

  it("leaves the rows as failed, not running, when the retry request itself fails", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ status: "failed", chunks: [chunk({ state: "failed", failure: "gateway refused" })] }),
    ];
    fakeArchive.retryFailure = new MarketDataError("upstream", "market-data is not reachable");
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /retry job/i }));

    // The reason stays with the decision it explains, and the dialog stays open.
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/market-data is not reachable/i)).toBeInTheDocument();
    expect(screen.getByTestId("history-1-US100-MINUTE")).toBeInTheDocument();
    expect(screen.queryByText("running")).not.toBeInTheDocument();
  });
});

describe("CollectionHistoryView — removing an entry from the history", () => {
  it("removes the job's rows once the operator confirms, and only that job's", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ symbol: "US100", resolution: "MINUTE" }),
      row({ symbol: "GOLD", resolution: "HOUR" }),
      row({ jobId: 2, symbol: "US100", resolution: "HOUR" }),
    ];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /remove from history/i }));
    // The sentence that separates this from deleting a pair's data.
    expect(screen.getByText(/stay in the archive/i)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /^remove$/i }));

    expect(fakeArchive.deleteCalls).toEqual([1]);
    await waitFor(() =>
      expect(screen.queryByTestId("history-1-US100-MINUTE")).not.toBeInTheDocument(),
    );
    // Every pair of that job, not only the row it was opened from — and nothing else.
    expect(screen.queryByTestId("history-1-GOLD-HOUR")).not.toBeInTheDocument();
    expect(screen.getByTestId("history-2-US100-HOUR")).toBeInTheDocument();
  });

  it("does not offer removal while the job is still running, and says why", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [row({ status: "running", chunksDone: 0, chunksTotal: 2 })];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).queryByRole("button", { name: /remove from history/i }),
    ).not.toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be removed .* still running/i)).toBeInTheDocument();
  });

  it("keeps the rows and names the reason when the removal itself fails", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [row()];
    fakeArchive.deleteFailure = new MarketDataError("upstream", "market-data is not reachable");
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /remove from history/i }));
    await user.click(await screen.findByRole("button", { name: /^remove$/i }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/market-data is not reachable/i)).toBeInTheDocument();
    expect(screen.getByTestId("history-1-US100-MINUTE")).toBeInTheDocument();
  });
});

describe("CollectionHistoryView — a job that has stopped moving", () => {
  it("says how long nothing has happened, and marks a running pull that has stalled", async () => {
    const now = Math.floor(Date.now() / 1000);
    fakeArchive.rows = [
      row({ symbol: "US100", status: "running", chunksDone: 1, chunksTotal: 4, lastActivityAt: now - 42 * 60 }),
      row({ jobId: 2, symbol: "GOLD", status: "running", chunksDone: 1, chunksTotal: 4, lastActivityAt: now - 30 }),
    ];
    renderView();

    const stuck = await screen.findByTestId("history-1-US100-MINUTE");
    const working = screen.getByTestId("history-2-GOLD-MINUTE");

    // Visible on the row itself — no dialog, no log, no waiting forty minutes.
    expect(within(stuck).getByText(/nothing for 42 min/i)).toBeInTheDocument();
    expect(within(working).getByText(/nothing for under a minute/i)).toBeInTheDocument();
    expect(stuck).toHaveAttribute("data-stalled", "true");
    expect(working).toHaveAttribute("data-stalled", "false");
  });
});

describe("CollectionHistoryView — empty vs unreachable", () => {
  it("says nothing has been collected yet, and points to Instruments", async () => {
    renderView();

    expect(await screen.findByText(/nothing has been collected yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Instruments" })).toHaveAttribute(
      "href",
      "/instruments",
    );
  });

  it("tells an unreachable archive apart from an empty history", async () => {
    fakeArchive.listFailure = new MarketDataError("unreachable", "the archive is not reachable");
    renderView();

    expect(await screen.findByText(/collection history is unknown/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing has been collected yet/i)).not.toBeInTheDocument();
  });
});

describe("CollectionHistoryView — polling", () => {
  it("keeps the rows on screen when a refresh fails, and says the refresh failed", async () => {
    vi.useFakeTimers();
    fakeArchive.rows = [row()];
    renderView();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId("history-1-US100-MINUTE")).toBeInTheDocument();

    fakeArchive.listFailure = new Error("network blip");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(screen.getByTestId("history-1-US100-MINUTE")).toBeInTheDocument();
    expect(screen.getByText(/last refresh failed/i)).toBeInTheDocument();
  });
});
