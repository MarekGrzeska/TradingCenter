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
  it("shows one row per pair pulled, with when, range, candles and state", async () => {
    fakeArchive.rows = [row()];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText("US100")).toBeInTheDocument();
    expect(within(r).getByText("m1")).toBeInTheDocument();
    expect(within(r).getByText("done")).toBeInTheDocument();
    expect(within(r).getByText("1,000 candles")).toBeInTheDocument();
  });

  it("shows every resolution of the same instrument as its own row", async () => {
    fakeArchive.rows = [row({ resolution: "MINUTE" }), row({ jobId: 2, resolution: "HOUR" })];
    renderView();

    expect(await screen.findByTestId("history-1-US100-MINUTE")).toBeInTheDocument();
    expect(screen.getByTestId("history-2-US100-HOUR")).toBeInTheDocument();
  });

  it("shows multiple pulls of the same pair, newest first", async () => {
    fakeArchive.rows = [row({ jobId: 5, createdAt: 2000 }), row({ jobId: 4, createdAt: 1000 })];
    renderView();

    const found = await screen.findAllByTestId(/^history-/);
    expect(found.map((el) => el.getAttribute("data-testid"))).toEqual([
      "history-5-US100-MINUTE",
      "history-4-US100-MINUTE",
    ]);
  });

  it("puts the newest event first even when its symbol sorts later", async () => {
    // GOLD before US100 alphabetically, and after it in time. Time is what wins.
    fakeArchive.rows = [
      row({ jobId: 1, symbol: "GOLD", createdAt: 1000 }),
      row({ jobId: 2, symbol: "US100", createdAt: 2000 }),
    ];
    renderView();

    const found = await screen.findAllByTestId(/^history-/);
    expect(found.map((el) => el.getAttribute("data-testid"))).toEqual([
      "history-2-US100-MINUTE",
      "history-1-GOLD-MINUTE",
    ]);
  });

  it("orders events of the same moment the same way however they arrive", async () => {
    // The shape a wizard submission makes: several pairs created together, so every
    // `createdAt` is identical. The two lists behind this view come from independent
    // polls, so a stable sort over an unstable input order guarantees nothing — the
    // tiebreak has to be derived from the data.
    const together = [
      row({ jobId: 1, symbol: "US100", resolution: "HOUR", createdAt: 5000 }),
      row({ jobId: 2, symbol: "GOLD", resolution: "MINUTE", createdAt: 5000 }),
      row({ jobId: 3, symbol: "US100", resolution: "MINUTE", createdAt: 5000 }),
    ];
    const expected = [
      "history-2-GOLD-MINUTE",
      "history-3-US100-MINUTE",
      "history-1-US100-HOUR",
    ];

    fakeArchive.rows = together;
    const first = renderView();
    expect(
      (await screen.findAllByTestId(/^history-/)).map((el) => el.getAttribute("data-testid")),
    ).toEqual(expected);
    first.unmount();

    fakeArchive.rows = [...together].reverse();
    renderView();
    expect(
      (await screen.findAllByTestId(/^history-/)).map((el) => el.getAttribute("data-testid")),
    ).toEqual(expected);
  });

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
    expect(within(r).getByText(/25% \(2\/8 chunks\)/)).toBeInTheDocument();
    expect(within(r).getByText(/4,000 candles so far/)).toBeInTheDocument();
  });

  it("says how far back the work actually got when it fell short of the range asked for", async () => {
    // The provider turned out to have nothing below the second chunk, so the older ones
    // were skipped. "2024 → today, 0 candles" reads as a failure and is a correct answer.
    fakeArchive.rows = [
      row({
        candlesWritten: 500,
        chunksDone: 1,
        chunksTotal: 2,
        chunks: [
          chunk({ id: 1, state: "done", chunkStart: 1785542400, chunkEnd: 1785600000 }),
          chunk({ id: 2, state: "skipped", chunkStart: 1700000000, chunkEnd: 1785542400 }),
        ],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText(/collected from/)).toBeInTheDocument();
  });

  it("says nothing was reachable when every chunk was skipped", async () => {
    fakeArchive.rows = [
      row({
        candlesWritten: 0,
        chunksDone: 1,
        chunksTotal: 1,
        chunks: [chunk({ state: "skipped" })],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText(/nothing in this range to collect/)).toBeInTheDocument();
  });

  it("stays quiet when the work covered everything it was asked for", async () => {
    fakeArchive.rows = [row()];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByText(/collected from/)).not.toBeInTheDocument();
    expect(within(r).queryByText(/nothing in this range/)).not.toBeInTheDocument();
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

  it("does not call a partially failed job shallow", async () => {
    fakeArchive.rows = [
      row({
        status: "partial",
        candlesWritten: 500,
        chunksDone: 1,
        chunksTotal: 2,
        chunks: [
          chunk({ id: 1, state: "done", chunkStart: 1785542400, chunkEnd: 1785600000 }),
          chunk({ id: 2, state: "failed", chunkStart: 1700000000, chunkEnd: 1785542400 }),
        ],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByText(/collected from/)).not.toBeInTheDocument();
  });

  it("does not call a job shallow while its older chunks are still queued", async () => {
    fakeArchive.rows = [
      row({
        status: "running",
        chunksDone: 1,
        chunksTotal: 2,
        chunks: [
          chunk({ id: 1, state: "done", chunkStart: 1785542400, chunkEnd: 1785600000 }),
          chunk({ id: 2, state: "pending", chunkStart: 1700000000, chunkEnd: 1785542400 }),
        ],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByText(/collected from/)).not.toBeInTheDocument();
  });
});

describe("CollectionHistoryView — deletions (delete-archived-pair-data)", () => {
  it("shows a deletion alongside a pull, newest first", async () => {
    fakeArchive.rows = [row({ jobId: 1, createdAt: 1000 })];
    fakeArchive.deletions = [deletion({ deletedAt: 2000 })];
    renderView();

    const found = await screen.findAllByTestId(/^(history|deletion)-/);
    expect(found.map((el) => el.getAttribute("data-testid"))).toEqual([
      `deletion-US100-MINUTE-2000`,
      "history-1-US100-MINUTE",
    ]);
  });

  it("puts a deletion above an older pull of a different instrument", async () => {
    // The reason the tab exists to be glanced at: whatever just happened is the top row,
    // even when it happened to an instrument whose name sorts last.
    fakeArchive.rows = [row({ jobId: 1, symbol: "GOLD", createdAt: 1000 })];
    fakeArchive.deletions = [deletion({ symbol: "US100", deletedAt: 2000 })];
    renderView();

    const found = await screen.findAllByTestId(/^(history|deletion)-/);
    expect(found.map((el) => el.getAttribute("data-testid"))).toEqual([
      "deletion-US100-MINUTE-2000",
      "history-1-GOLD-MINUTE",
    ]);
  });

  it("names the pair, when, how many candles, and the range they covered", async () => {
    fakeArchive.deletions = [deletion({ candlesRemoved: 42 })];
    renderView();

    const r = await screen.findByTestId("deletion-US100-MINUTE-1786200000");
    expect(within(r).getByText("US100")).toBeInTheDocument();
    expect(within(r).getByText("m1")).toBeInTheDocument();
    expect(within(r).getByText(/−42 candles/)).toBeInTheDocument();
    expect(within(r).getByText(/→/)).toBeInTheDocument();
  });

  it("shows a null range as a dash rather than a fabricated one", async () => {
    fakeArchive.deletions = [deletion({ candlesRemoved: 0, removedFrom: null, removedTo: null })];
    renderView();

    const r = await screen.findByTestId("deletion-US100-MINUTE-1786200000");
    expect(within(r).getByText("—")).toBeInTheDocument();
  });

  it("does not read as a success or a failure", async () => {
    fakeArchive.deletions = [deletion()];
    renderView();

    const r = await screen.findByTestId("deletion-US100-MINUTE-1786200000");
    const label = within(r).getByText("deleted");
    expect(label).not.toHaveClass("text-up");
    expect(label).not.toHaveClass("text-critical");
    expect(label).not.toHaveClass("text-warning");
  });

  it("keeps an instrument's history readable after it was deleted in full", async () => {
    fakeArchive.rows = [row()];
    fakeArchive.deletions = [deletion()];
    renderView();

    expect(await screen.findByTestId("history-1-US100-MINUTE")).toBeInTheDocument();
    expect(screen.getByTestId("deletion-US100-MINUTE-1786200000")).toBeInTheDocument();
  });

  it("counts a deletion on its own as history, not an empty tab", async () => {
    fakeArchive.deletions = [deletion()];
    renderView();

    expect(await screen.findByTestId("deletion-US100-MINUTE-1786200000")).toBeInTheDocument();
    expect(screen.queryByText(/nothing has been collected yet/i)).not.toBeInTheDocument();
  });
});

describe("CollectionHistoryView — success vs partial coverage", () => {
  it("marks a full success distinctly, with candles and the covered range", async () => {
    fakeArchive.rows = [
      row({
        status: "succeeded",
        candlesWritten: 5000,
        chunks: [
          chunk({ chunkStart: 1000, chunkEnd: 2000 }),
          chunk({ id: 2, chunkStart: 2000, chunkEnd: 3000 }),
        ],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).getByText("done")).toHaveClass("text-up");
    expect(within(r).getByText(/→/)).toBeInTheDocument();
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
    expect(within(dialog).getByText("US100")).toBeInTheDocument();
    expect(within(dialog).getByText("GOLD")).toBeInTheDocument();
    expect(within(dialog).getByText(/2 pairs/i)).toBeInTheDocument();
  });

  it("opens from the keyboard too, without a pointer", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [row()];
    renderView();

    await screen.findByTestId("history-1-US100-MINUTE");
    await user.tab();

    expect(screen.getByRole("button", { name: /job 1 details/i })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("opens nothing from a deletion entry, which came from no job", async () => {
    const user = userEvent.setup();
    fakeArchive.deletions = [deletion()];
    renderView();

    await user.click(await screen.findByTestId("deletion-US100-MINUTE-1786200000"));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps retry off the pair's row, where it would promise less than it does", async () => {
    fakeArchive.rows = [
      row({
        status: "failed",
        chunksDone: 0,
        chunksTotal: 1,
        chunks: [chunk({ state: "failed", failure: "gateway refused" })],
      }),
    ];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
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
    // And why it failed, where the decision to retry is being made.
    expect(within(dialog).getByText("gateway refused")).toBeInTheDocument();
    expect(fakeArchive.retryCalls).toHaveLength(0);

    fakeArchive.rows = [row({ status: "running", chunksDone: 0, chunksTotal: 1 })];
    await user.click(screen.getByRole("button", { name: /retry job/i }));

    expect(fakeArchive.retryCalls).toEqual([1]);
    await waitFor(() => expect(screen.getByText("running")).toBeInTheDocument());
  });

  it("does not offer retry for a fully succeeded pull", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [row({ status: "succeeded" })];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
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
  it("removes the job's rows once the operator confirms", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ symbol: "US100", resolution: "MINUTE" }),
      row({ symbol: "GOLD", resolution: "HOUR" }),
      row({ jobId: 2, symbol: "US100", resolution: "HOUR" }),
    ];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /remove from history/i }));
    await user.click(await screen.findByRole("button", { name: /^remove$/i }));

    expect(fakeArchive.deleteCalls).toEqual([1]);
    await waitFor(() =>
      expect(screen.queryByTestId("history-1-US100-MINUTE")).not.toBeInTheDocument(),
    );
    // Every pair of that job, not only the row it was opened from — and nothing else.
    expect(screen.queryByTestId("history-1-GOLD-HOUR")).not.toBeInTheDocument();
    expect(screen.getByTestId("history-2-US100-HOUR")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says how much it covers and that the candles stay, before removing anything", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ symbol: "US100", resolution: "MINUTE" }),
      row({ symbol: "GOLD", resolution: "HOUR" }),
    ];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /remove from history/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/2 pairs and 2 chunks/i)).toBeInTheDocument();
    // The sentence that separates this from deleting a pair's data.
    expect(within(dialog).getByText(/stay in the archive/i)).toBeInTheDocument();
    expect(fakeArchive.deleteCalls).toHaveLength(0);
  });

  it("keeps removal off the pair's row, where it would promise less than it does", async () => {
    fakeArchive.rows = [row()];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
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

  it("goes back to the job rather than closing everything when the question is declined", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [row()];
    renderView();

    await user.click(await screen.findByTestId("history-1-US100-MINUTE"));
    await user.click(await screen.findByRole("button", { name: /remove from history/i }));
    await user.click(await screen.findByRole("button", { name: /cancel/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove from history/i })).toBeInTheDocument();
    expect(fakeArchive.deleteCalls).toHaveLength(0);
  });
});

describe("CollectionHistoryView — a job that has stopped moving", () => {
  it("says how long nothing has happened, and marks a running pull that has stalled", async () => {
    const now = Math.floor(Date.now() / 1000);
    fakeArchive.rows = [
      row({
        symbol: "US100",
        status: "running",
        chunksDone: 1,
        chunksTotal: 4,
        lastActivityAt: now - 42 * 60,
      }),
      row({
        jobId: 2,
        symbol: "GOLD",
        status: "running",
        chunksDone: 1,
        chunksTotal: 4,
        lastActivityAt: now - 30,
      }),
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

  it("says nothing about idleness for a pull that has finished", async () => {
    fakeArchive.rows = [row({ status: "succeeded", lastActivityAt: 1785542500 })];
    renderView();

    const r = await screen.findByTestId("history-1-US100-MINUTE");
    expect(within(r).queryByText(/nothing for/i)).not.toBeInTheDocument();
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
  it("refreshes on its own every 10 seconds, and stops once the tab is left", async () => {
    vi.useFakeTimers();
    fakeArchive.rows = [row({ status: "running", chunksDone: 1, chunksTotal: 4 })];
    const { unmount } = renderView();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText(/25% \(1\/4 chunks\)/)).toBeInTheDocument();
    const afterFirstRead = fakeArchive.listCalls;

    // Pinned from both sides, so this still constrains the interval if it changes:
    // a longer one would not have fired by 10s, a shorter one would have fired before it.
    fakeArchive.rows = [row({ status: "running", chunksDone: 2, chunksTotal: 4 })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_900);
    });
    expect(fakeArchive.listCalls).toBe(afterFirstRead);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(fakeArchive.listCalls).toBe(afterFirstRead + 1);
    expect(screen.getByText(/50% \(2\/4 chunks\)/)).toBeInTheDocument();

    const callsBeforeUnmount = fakeArchive.listCalls;
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fakeArchive.listCalls).toBe(callsBeforeUnmount);
  });

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
