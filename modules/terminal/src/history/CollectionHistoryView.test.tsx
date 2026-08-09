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
  listCalls = 0;
  retryCalls: number[] = [];

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
    return { id: jobId, createdAt: 0, requestedFrom: 0, attempt: 2, status: "running", chunksDone: 0, chunksTotal: 0, candlesWritten: 0, runningPair: null, chunks: [] };
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
    expect(within(r).getByText("MINUTE")).toBeInTheDocument();
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
    expect(within(r).getByText("MINUTE")).toBeInTheDocument();
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

describe("CollectionHistoryView — retry", () => {
  it("says what will be retried before doing it, and moves the row to running once queued", async () => {
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

    await user.click(await screen.findByRole("button", { name: /retry us100 minute/i }));
    expect(screen.getByText(/retry 1 chunk for us100 minute/i)).toBeInTheDocument();
    expect(fakeArchive.retryCalls).toHaveLength(0);

    fakeArchive.rows = [row({ status: "running", chunksDone: 0, chunksTotal: 1 })];
    await user.click(screen.getByRole("button", { name: /^retry$/i }));

    expect(fakeArchive.retryCalls).toEqual([1]);
    await waitFor(() => expect(screen.getByText("running")).toBeInTheDocument());
  });

  it("does not offer retry for a fully succeeded pull", async () => {
    fakeArchive.rows = [row({ status: "succeeded" })];
    renderView();

    await screen.findByTestId("history-1-US100-MINUTE");
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("leaves the row as failed, not running, when the retry request itself fails", async () => {
    const user = userEvent.setup();
    fakeArchive.rows = [
      row({ status: "failed", chunks: [chunk({ state: "failed", failure: "gateway refused" })] }),
    ];
    fakeArchive.retryFailure = new MarketDataError("upstream", "market-data is not reachable");
    renderView();

    await user.click(await screen.findByRole("button", { name: /retry us100 minute/i }));
    await user.click(screen.getByRole("button", { name: /^retry$/i }));

    expect(await screen.findByText(/market-data is not reachable/i)).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.queryByText("running")).not.toBeInTheDocument();
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
