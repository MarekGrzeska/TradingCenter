import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createArchiveSource, readRefusalFromPairs, translateMessage } from "./archive";
import { MarketDataError } from "./types";
import type { Resolution, TrackedPair } from "./types";

const HTTP_BASE = "http://archive.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function source() {
  return createArchiveSource(HTTP_BASE, "ws://archive.test/ws");
}

function signal() {
  return new AbortController().signal;
}

/** One candle as the subscription spells it — the archive's storage shape. */
function streamCandle(periodStart: string, close: number, forming = false) {
  return {
    symbol: "US100",
    resolution: "MINUTE_5",
    period_start: periodStart,
    open: close,
    high: close + 1,
    low: close - 1,
    close,
    volume: 10,
    price_side: "bid",
    source: forming ? "stream" : "history",
    forming,
  };
}

describe("archive.history (the range read)", () => {
  it("asks for the window in ISO and answers in epoch seconds", async () => {
    server.use(
      http.get(`${HTTP_BASE}/candles/US100`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("resolution")).toBe("MINUTE_5");
        expect(url.searchParams.get("from")).toBe("2026-08-07T14:00:00.000Z");
        expect(url.searchParams.get("to")).toBe("2026-08-07T15:00:00.000Z");
        return HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE_5",
          price_side: "bid",
          derived: true,
          candles: [
            { time: "2026-08-07T14:35:00Z", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
          ],
          uncovered: [],
        });
      }),
    );

    const bars = await source().history(
      { symbol: "US100", resolution: "MINUTE_5", from: 1786111200, to: 1786114800 },
      signal(),
    );
    expect(bars).toEqual([
      { time: 1786113300, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, forming: false },
    ]);
  });

  it("drops a candle missing an OHLC field instead of faking a zero", async () => {
    server.use(
      http.get(`${HTTP_BASE}/candles/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          price_side: "bid",
          derived: false,
          candles: [
            {
              time: "2026-08-07T14:35:00Z",
              open: null,
              high: null,
              low: null,
              close: null,
              volume: null,
            },
            { time: "2026-08-07T14:40:00Z", open: 1, high: 1, low: 1, close: 1, volume: null },
          ],
          uncovered: [],
        }),
      ),
    );

    const bars = await source().history(
      { symbol: "US100", resolution: "MINUTE", from: 0, to: 1 },
      signal(),
    );
    expect(bars).toHaveLength(1);
    expect(bars[0].time).toBe(1786113600);
  });

  it("maps a 404 to a not-found error naming the symbol", async () => {
    server.use(
      http.get(`${HTTP_BASE}/candles/NOPE`, () =>
        HttpResponse.json({ detail: "unknown instrument 'NOPE'" }, { status: 404 }),
      ),
    );

    const call = source().history(
      { symbol: "NOPE", resolution: "MINUTE", from: 0, to: 1 },
      signal(),
    );
    await expect(call).rejects.toBeInstanceOf(MarketDataError);
    await expect(call).rejects.toMatchObject({
      kind: "not-found",
      message: "unknown instrument 'NOPE'",
    });
  });

  it("says the archive is unreachable rather than surfacing a transport error", async () => {
    server.use(http.get(`${HTTP_BASE}/candles/US100`, () => HttpResponse.error()));

    await expect(
      source().history({ symbol: "US100", resolution: "MINUTE", from: 0, to: 1 }, signal()),
    ).rejects.toMatchObject({
      kind: "unreachable",
      message: "the candle archive is not reachable",
    });
  });
});

describe("archive subscription messages", () => {
  it("turns the opening snapshot into one event carrying the series and the forming bar", () => {
    const events = translateMessage(
      JSON.stringify({
        kind: "snapshot",
        symbol: "US100",
        resolution: "MINUTE_5",
        candles: [streamCandle("2026-08-07T14:35:00Z", 1), streamCandle("2026-08-07T14:40:00Z", 2)],
        forming: streamCandle("2026-08-07T14:45:00Z", 3, true),
      }),
    );

    expect(events).toHaveLength(1);
    const [event] = events;
    expect(event.kind).toBe("snapshot");
    if (event.kind !== "snapshot") return;
    expect(event.bars.map((b) => b.time)).toEqual([1786113300, 1786113600]);
    // Settled candles are settled whatever the archive stored about them; only
    // the period still being built is marked.
    expect(event.bars.every((b) => !b.forming)).toBe(true);
    expect(event.forming).toMatchObject({ time: 1786113900, close: 3, forming: true });
  });

  it("carries a snapshot with nothing in it rather than pretending it never came", () => {
    const events = translateMessage(
      JSON.stringify({ kind: "snapshot", symbol: "US100", resolution: "MINUTE", candles: [] }),
    );
    expect(events).toEqual([{ kind: "snapshot", bars: [], forming: null }]);
  });

  it("marks a change as forming or settled from the candle, not the frame", () => {
    const forming = translateMessage(
      JSON.stringify({
        kind: "candle",
        symbol: "US100",
        resolution: "MINUTE_5",
        candle: streamCandle("2026-08-07T14:45:00Z", 3, true),
      }),
    );
    expect(forming).toEqual([
      {
        kind: "bar",
        bar: { time: 1786113900, open: 3, high: 4, low: 2, close: 3, volume: 10, forming: true },
      },
    ]);

    const settled = translateMessage(
      JSON.stringify({
        kind: "candle",
        symbol: "US100",
        resolution: "MINUTE_5",
        candle: streamCandle("2026-08-07T14:45:00Z", 3, false),
      }),
    );
    expect(settled[0]).toMatchObject({ kind: "bar", bar: { forming: false } });
  });

  // The range read spells the field `time` and the subscription `period_start`. A bar landing on a different
  // axis point by road would draw the same period twice (terminal-market-data spec, "Znaczniki czasu…").
  it("puts a candle at the same instant whichever road it arrived by", async () => {
    server.use(
      http.get(`${HTTP_BASE}/candles/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE_5",
          price_side: "bid",
          derived: true,
          candles: [
            { time: "2026-08-07T14:45:00Z", open: 3, high: 4, low: 2, close: 3, volume: 10 },
          ],
          uncovered: [],
        }),
      ),
    );

    const [fromRead] = await source().history(
      { symbol: "US100", resolution: "MINUTE_5", from: 0, to: 1 },
      signal(),
    );
    const [event] = translateMessage(
      JSON.stringify({
        kind: "candle",
        symbol: "US100",
        resolution: "MINUTE_5",
        candle: streamCandle("2026-08-07T14:45:00Z", 3),
      }),
    );

    expect(event.kind).toBe("bar");
    if (event.kind !== "bar") return;
    expect(event.bar.time).toBe(fromRead.time);
  });

  it("ignores a message kind it does not know, rather than failing on it", () => {
    // A kind the archive adds one day must not break a chart that predates it.
    expect(translateMessage(JSON.stringify({ kind: "heartbeat" }))).toEqual([]);
    expect(translateMessage("not json at all")).toEqual([]);
  });
});

describe("archive pair management", () => {
  it("lists what is collected, with how collection is going", async () => {
    server.use(
      http.get(`${HTTP_BASE}/pairs`, () =>
        HttpResponse.json([
          {
            symbol: "US100",
            resolution: "MINUTE",
            added_at: "2026-08-01T10:00:00Z",
            collect_from: "2026-07-25T10:00:00Z",
            earliest_candle: "2026-07-26T00:00:00Z",
            latest_candle: "2026-08-07T14:40:00Z",
            collection: "collecting",
            candle_count: 12431,
            estimated_bytes: 1193376,
          },
          {
            symbol: "GOLD",
            resolution: "HOUR",
            added_at: "2026-08-02T10:00:00Z",
            collect_from: "2026-06-02T10:00:00Z",
            earliest_candle: null,
            latest_candle: null,
            collection: "never_collected",
            candle_count: 0,
            estimated_bytes: 0,
          },
        ]),
      ),
    );

    const pairs = await source().listPairs(signal());
    expect(pairs).toEqual([
      {
        symbol: "US100",
        resolution: "MINUTE",
        addedAt: 1785578400,
        collectFrom: 1784973600,
        earliestCandle: 1785024000,
        latestCandle: 1786113600,
        collection: "collecting",
        candleCount: 12431,
        estimatedBytes: 1193376,
      },
      {
        symbol: "GOLD",
        resolution: "HOUR",
        addedAt: 1785664800,
        collectFrom: 1780394400,
        earliestCandle: null,
        latestCandle: null,
        collection: "never_collected",
        candleCount: 0,
        estimatedBytes: 0,
      },
    ]);
  });

  it("sends every pair and the start moment as one body, and reads back per-pair results", async () => {
    server.use(
      http.post(`${HTTP_BASE}/pairs`, async ({ request }) => {
        expect(await request.json()).toEqual({
          pairs: [
            { symbol: "US100", resolution: "MINUTE" },
            { symbol: "US100", resolution: "HOUR" },
          ],
          collect_from: "2026-08-01T00:00:00.000Z",
        });
        return HttpResponse.json(
          {
            results: [
              {
                symbol: "US100",
                resolution: "MINUTE",
                pair: {
                  symbol: "US100",
                  resolution: "MINUTE",
                  added_at: "2026-08-08T09:00:00Z",
                  collect_from: "2026-08-01T00:00:00Z",
                  earliest_candle: null,
                  latest_candle: null,
                  collection: "never_collected",
                },
                refused: null,
              },
              {
                symbol: "US100",
                resolution: "HOUR",
                pair: null,
                refused: "already being archived",
              },
            ],
            job_id: 42,
          },
          { status: 201 },
        );
      }),
    );

    const result = await source().trackPairs(
      [
        { symbol: "US100", resolution: "MINUTE" },
        { symbol: "US100", resolution: "HOUR" },
      ],
      1785542400,
      signal(),
    );

    expect(result.jobId).toBe(42);
    expect(result.results[0]).toMatchObject({ symbol: "US100", refused: null });
    expect(result.results[0].pair).toMatchObject({ symbol: "US100", collection: "never_collected" });
    expect(result.results[1]).toMatchObject({ symbol: "US100", pair: null, refused: "already being archived" });
  });

  it("omits collect_from when none was given, so the archive falls back to its default depth", async () => {
    server.use(
      http.post(`${HTTP_BASE}/pairs`, async ({ request }) => {
        expect(await request.json()).toEqual({ pairs: [{ symbol: "US100", resolution: "MINUTE" }] });
        return HttpResponse.json({ results: [], job_id: 1 }, { status: 201 });
      }),
    );

    await source().trackPairs([{ symbol: "US100", resolution: "MINUTE" }], null, signal());
  });

  // The gateway holds one provider connection per pair and the provider limits sessions, so the ceiling is
  // what the panel exists to be refused by. A generic failure would leave the operator nothing to act on.
  it("keeps the reason a top-level refusal gives, and marks it as a refusal rather than a fault", async () => {
    server.use(
      http.post(`${HTTP_BASE}/pairs`, () =>
        HttpResponse.json(
          { detail: "20 pairs are already collected; raise MAX_TRACKED_PAIRS to add more" },
          { status: 409 },
        ),
      ),
    );

    const call = source().trackPairs([{ symbol: "US100", resolution: "MINUTE" }], null, signal());
    await expect(call).rejects.toMatchObject({
      kind: "refused",
      message: "20 pairs are already collected; raise MAX_TRACKED_PAIRS to add more",
    });
  });

  it("tells a gateway that is down apart from an archive that is down", async () => {
    server.use(
      http.post(`${HTTP_BASE}/pairs`, () =>
        HttpResponse.json({ detail: "capital-gateway did not answer" }, { status: 504 }),
      ),
    );

    // 504: the archive answered — it is the thing behind it that did not, and retrying is worth doing.
    // Compare `unreachable`, where the archive itself never answered at all.
    const call = source().trackPairs([{ symbol: "US100", resolution: "MINUTE" }], null, signal());
    await expect(call).rejects.toMatchObject({ kind: "upstream" });
  });

  it("deletes with the resolution in the query, and reads back what was removed", async () => {
    let asked: URL | null = null;
    server.use(
      http.delete(`${HTTP_BASE}/pairs/US100`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          deleted_at: "2026-08-08T10:00:00Z",
          candles_removed: 42,
          removed_from: "2026-08-01T00:00:00Z",
          removed_to: "2026-08-07T14:40:00Z",
        });
      }),
    );

    const deletion = await source().deletePair("US100", "MINUTE", signal());
    expect(asked!.searchParams.get("resolution")).toBe("MINUTE");
    expect(deletion).toEqual({
      symbol: "US100",
      resolution: "MINUTE",
      deletedAt: 1786183200,
      candlesRemoved: 42,
      removedFrom: 1785542400,
      removedTo: 1786113600,
    });
  });

  it("deletes a pair that had never collected anything, with a null range", async () => {
    server.use(
      http.delete(`${HTTP_BASE}/pairs/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          deleted_at: "2026-08-08T10:00:00Z",
          candles_removed: 0,
          removed_from: null,
          removed_to: null,
        }),
      ),
    );

    const deletion = await source().deletePair("US100", "MINUTE", signal());
    expect(deletion.candlesRemoved).toBe(0);
    expect(deletion.removedFrom).toBeNull();
    expect(deletion.removedTo).toBeNull();
  });

  it("lists deletions, narrowed by symbol and resolution when given", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/deletions`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json([
          {
            symbol: "US100",
            resolution: "MINUTE",
            deleted_at: "2026-08-08T10:00:00Z",
            candles_removed: 5,
            removed_from: "2026-08-01T00:00:00Z",
            removed_to: "2026-08-07T14:40:00Z",
          },
        ]);
      }),
    );

    const deletions = await source().listDeletions("US100", "MINUTE", signal());
    expect(asked!.searchParams.get("symbol")).toBe("US100");
    expect(asked!.searchParams.get("resolution")).toBe("MINUTE");
    expect(deletions).toHaveLength(1);
    expect(deletions[0].symbol).toBe("US100");
  });

  it("lists every deletion when neither symbol nor resolution is given", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/deletions`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json([]);
      }),
    );

    await source().listDeletions(null, null, signal());
    expect(asked!.search).toBe("");
  });

  it("reads coverage, including the boundary the provider's history ends at", async () => {
    server.use(
      http.get(`${HTTP_BASE}/coverage/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          ranges: [
            { from: "2026-08-01T00:00:00Z", to: "2026-08-07T14:40:00Z", history_ended: true },
          ],
          earliest_reachable: "2026-08-01T00:00:00Z",
        }),
      ),
    );

    const coverage = await source().coverage("US100", "MINUTE", signal());
    expect(coverage).toEqual({
      symbol: "US100",
      resolution: "MINUTE",
      ranges: [{ from: 1785542400, to: 1786113600, historyEnded: true }],
      earliestReachable: 1785542400,
    });
  });

  it("keeps 'not known yet' distinct from 'no limit' for the earliest reachable moment", async () => {
    server.use(
      http.get(`${HTTP_BASE}/coverage/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          ranges: [],
          earliest_reachable: null,
        }),
      ),
    );

    const coverage = await source().coverage("US100", "MINUTE", signal());
    expect(coverage.earliestReachable).toBeNull();
  });
});

describe("archive: reading a subscription's refusal off the tracked list", () => {
  const pair = (symbol: string, resolution: Resolution): TrackedPair => ({
    symbol,
    resolution,
    addedAt: 1785578400,
    collectFrom: 1785578400,
    earliestCandle: null,
    latestCandle: null,
    collection: "never_collected",
    candleCount: 0,
    estimatedBytes: 0,
  });

  // The archive refuses before the handshake, so the browser never learns why: the tracked list is the
  // second place to ask, and a pair missing from it is the one answer that means retrying cannot help.
  it("names the pair and where to fix it, when nobody is collecting it", () => {
    const reason = readRefusalFromPairs([pair("GOLD", "HOUR")], "US100", "MINUTE_5");
    expect(reason).toContain("US100 MINUTE_5");
    expect(reason).toContain("Instruments tab");
  });

  it("finds no reason to stop when the pair is on the list", () => {
    expect(
      readRefusalFromPairs([pair("US100", "MINUTE_5")], "US100", "MINUTE_5"),
    ).toBeNull();
  });

  // Same symbol, different resolution, is a different pair — collecting
  // US100 MINUTE_5 says nothing about US100 HOUR.
  it("matches on the resolution too, not the symbol alone", () => {
    expect(readRefusalFromPairs([pair("US100", "MINUTE_5")], "US100", "HOUR")).toContain(
      "US100 HOUR",
    );
  });
});

describe("archive: collection jobs", () => {
  it("prices a job without creating anything", async () => {
    server.use(
      http.post(`${HTTP_BASE}/jobs/estimate`, async ({ request }) => {
        expect(await request.json()).toEqual({
          pairs: [{ symbol: "US100", resolution: "MINUTE" }],
          collect_from: "2026-08-01T00:00:00.000Z",
        });
        return HttpResponse.json({
          pairs: [
            {
              symbol: "US100",
              resolution: "MINUTE",
              effective_from: "2026-08-01T00:00:00Z",
              clipped: false,
              estimated_candles: 10080,
              estimated_bytes: 967680,
              unknown: false,
            },
          ],
          total_estimated_candles: 10080,
          total_estimated_bytes: 967680,
        });
      }),
    );

    const estimate = await source().estimateJob(
      [{ symbol: "US100", resolution: "MINUTE" }],
      1785542400,
      signal(),
    );

    expect(estimate.totalEstimatedCandles).toBe(10080);
    expect(estimate.pairs[0]).toMatchObject({
      symbol: "US100",
      clipped: false,
      estimatedCandles: 10080,
    });
  });

  it("marks a symbol the gateway does not know, without a numeric moment", async () => {
    server.use(
      http.post(`${HTTP_BASE}/jobs/estimate`, () =>
        HttpResponse.json({
          pairs: [
            {
              symbol: "NOPE",
              resolution: "MINUTE",
              effective_from: null,
              clipped: false,
              estimated_candles: 0,
              estimated_bytes: 0,
              unknown: true,
            },
          ],
          total_estimated_candles: 0,
          total_estimated_bytes: 0,
        }),
      ),
    );

    const estimate = await source().estimateJob(
      [{ symbol: "NOPE", resolution: "MINUTE" }],
      1785542400,
      signal(),
    );

    expect(estimate.pairs[0].unknown).toBe(true);
    expect(estimate.pairs[0].effectiveFrom).toBeNull();
  });

  it("lists jobs narrowed to a pair, with the query string carrying the filter", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/jobs`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json([
          {
            job_id: 7,
            symbol: "US100",
            resolution: "MINUTE",
            created_at: "2026-08-08T09:00:00Z",
            requested_from: "2026-08-01T00:00:00Z",
            attempt: 1,
            status: "succeeded",
            chunks_done: 1,
            chunks_total: 1,
            candles_written: 10080,
            last_activity_at: "2026-08-08T09:05:00Z",
            chunks: [],
          },
        ]);
      }),
    );

    const jobs = await source().listJobs("US100", "MINUTE", signal());

    expect(asked!.searchParams.get("symbol")).toBe("US100");
    expect(asked!.searchParams.get("resolution")).toBe("MINUTE");
    expect(jobs).toEqual([
      {
        jobId: 7,
        symbol: "US100",
        resolution: "MINUTE",
        createdAt: 1786179600,
        requestedFrom: 1785542400,
        attempt: 1,
        status: "succeeded",
        chunksDone: 1,
        chunksTotal: 1,
        candlesWritten: 10080,
        lastActivityAt: 1786179900,
        chunks: [],
      },
    ]);
  });

  it("lists every job with no filter, and sends no query string", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/jobs`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json([]);
      }),
    );

    await source().listJobs(null, null, signal());

    expect(asked!.search).toBe("");
  });

  it("reads one job whole, including the pair presently in flight", async () => {
    server.use(
      http.get(`${HTTP_BASE}/jobs/7`, () =>
        HttpResponse.json({
          id: 7,
          created_at: "2026-08-08T09:00:00Z",
          requested_from: "2026-08-01T00:00:00Z",
          attempt: 1,
          status: "running",
          chunks_done: 1,
          chunks_total: 3,
          candles_written: 5000,
          last_activity_at: "2026-08-08T09:00:05Z",
          running_pair: { symbol: "US100", resolution: "MINUTE" },
          chunks: [
            {
              id: 1,
              symbol: "US100",
              resolution: "MINUTE",
              chunk_start: "2026-08-07T00:00:00Z",
              chunk_end: "2026-08-08T00:00:00Z",
              state: "done",
              attempt: 1,
              candles_written: 5000,
              requests: 5,
              failure: null,
              started_at: "2026-08-08T09:00:01Z",
              finished_at: "2026-08-08T09:00:05Z",
            },
          ],
        }),
      ),
    );

    const job = await source().readJob(7, signal());

    expect(job.runningPair).toEqual({ symbol: "US100", resolution: "MINUTE" });
    expect(job.chunks[0]).toMatchObject({ id: 1, state: "done", candlesWritten: 5000, failure: null });
  });

  it("retries a job and reads back the reset chunks", async () => {
    let method = "";
    server.use(
      http.post(`${HTTP_BASE}/jobs/7/retry`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({
          id: 7,
          created_at: "2026-08-08T09:00:00Z",
          requested_from: "2026-08-01T00:00:00Z",
          attempt: 2,
          status: "running",
          chunks_done: 1,
          chunks_total: 2,
          candles_written: 5000,
          last_activity_at: "2026-08-08T09:00:05Z",
          running_pair: null,
          chunks: [],
        });
      }),
    );

    const job = await source().retryJob(7, signal());

    expect(method).toBe("POST");
    expect(job.attempt).toBe(2);
  });

  it("marks a retry with nothing to retry as a refusal", async () => {
    server.use(
      http.post(`${HTTP_BASE}/jobs/7/retry`, () =>
        HttpResponse.json({ detail: "job 7 has no failed or interrupted chunk" }, { status: 409 }),
      ),
    );

    await expect(source().retryJob(7, signal())).rejects.toMatchObject({ kind: "refused" });
  });

  it("marks retrying an unknown job as not-found", async () => {
    server.use(
      http.post(`${HTTP_BASE}/jobs/999/retry`, () =>
        HttpResponse.json({ detail: "no collection job with id 999" }, { status: 404 }),
      ),
    );

    await expect(source().retryJob(999, signal())).rejects.toMatchObject({ kind: "not-found" });
  });

  it("deletes a job with no body to read back", async () => {
    // The archive answers 204, so asking for JSON here would fail on the success
    // path — the one thing worth pinning about this call.
    let method = "";
    server.use(
      http.delete(`${HTTP_BASE}/jobs/7`, ({ request }) => {
        method = request.method;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(source().deleteJob(7, signal())).resolves.toBeUndefined();
    expect(method).toBe("DELETE");
  });

  it("marks deleting a job that is still running as a refusal", async () => {
    server.use(
      http.delete(`${HTTP_BASE}/jobs/7`, () =>
        HttpResponse.json(
          { detail: "job 7 still has chunks pending or running" },
          { status: 409 },
        ),
      ),
    );

    await expect(source().deleteJob(7, signal())).rejects.toMatchObject({ kind: "refused" });
  });

  it("marks deleting an unknown job as not-found", async () => {
    server.use(
      http.delete(`${HTTP_BASE}/jobs/999`, () =>
        HttpResponse.json({ detail: "no collection job with id 999" }, { status: 404 }),
      ),
    );

    await expect(source().deleteJob(999, signal())).rejects.toMatchObject({ kind: "not-found" });
  });
});

/**
 * A browser cannot put a header on a WebSocket handshake, so the archive answers with a ticket good once.
 * These check the two properties that rests on: the token never reaches the address, no ticket is used twice.
 */
describe("archive.subscribe (the ticket the handshake costs)", () => {
  /** Constructible on purpose: the hub reaches the socket through `new
   *  WebSocket(url)`, and an arrow function cannot be `new`-ed. */
  function socketSpy() {
    const urls: string[] = [];
    const opened: FakeBrowserSocket[] = [];
    function FakeBrowserSocket(this: FakeBrowserSocket, url: string) {
      urls.push(url);
      this.onopen = null;
      this.onclose = null;
      this.onerror = null;
      this.onmessage = null;
      this.close = () => {};
      opened.push(this);
    }
    return { urls, opened, factory: FakeBrowserSocket as unknown as typeof WebSocket };
  }

  interface FakeBrowserSocket {
    onopen: (() => void) | null;
    onclose: ((event: { code: number; reason: string }) => void) | null;
    onerror: (() => void) | null;
    onmessage: ((event: { data: string }) => void) | null;
    close: () => void;
  }

  /** The hub asks for a ticket before it dials, so the socket is constructed a microtask *after* `subscribe`
   *  returns — restoring the global inside a synchronous block would put the real one back first. */
  let restoreWebSocket: (() => void) | null = null;

  function installFakeWebSocket(factory: typeof WebSocket): void {
    const original = globalThis.WebSocket;
    (globalThis as { WebSocket: unknown }).WebSocket = factory;
    restoreWebSocket = () => {
      (globalThis as { WebSocket: unknown }).WebSocket = original;
    };
  }

  afterEach(() => {
    restoreWebSocket?.();
    restoreWebSocket = null;
  });

  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("asks for a ticket and puts it in the address, never the token", async () => {
    let authorization: string | null = null;
    let issued = 0;
    server.use(
      http.post(`${HTTP_BASE}/stream-tickets`, ({ request }) => {
        authorization = request.headers.get("Authorization");
        issued += 1;
        return HttpResponse.json({ ticket: "ticket-one", expires_in_seconds: 30 });
      }),
    );
    const spy = socketSpy();
    const identity = {
      state: () => "signed-in" as const,
      subscribe: () => () => {},
      token: async () => "operator-token",
      refresh: async () => "operator-token",
      signIn: () => {},
    };

    installFakeWebSocket(spy.factory);
    createArchiveSource(HTTP_BASE, "ws://archive.test/ws", identity).subscribe(
      "US100",
      "MINUTE_5" as Resolution,
      () => {},
    );
    await settle();

    expect(issued).toBe(1);
    // The token proves who is asking, over HTTP, where a header exists…
    expect(authorization).toBe("Bearer operator-token");
    // …and the address carries only what is worthless a second later.
    expect(spy.urls[0]).toContain("ticket=ticket-one");
    expect(spy.urls[0]).not.toContain("operator-token");
  });

  it("asks for a new ticket on every attempt, because a spent one is not a ticket", async () => {
    let issued = 0;
    server.use(
      http.post(`${HTTP_BASE}/stream-tickets`, () => {
        issued += 1;
        return HttpResponse.json({ ticket: `ticket-${issued}`, expires_in_seconds: 30 });
      }),
      // The reconnect loop asks this before settling in; answering keeps the
      // test about tickets rather than about diagnosis.
      http.get(`${HTTP_BASE}/pairs`, () =>
        HttpResponse.json([
          {
            symbol: "US100",
            resolution: "MINUTE_5",
            added_at: "2026-08-09T12:00:00Z",
            collect_from: "2026-08-09T12:00:00Z",
            earliest_candle: null,
            latest_candle: null,
            collection: "collecting",
          },
        ]),
      ),
    );
    const spy = socketSpy();

    installFakeWebSocket(spy.factory);
    createArchiveSource(HTTP_BASE, "ws://archive.test/ws").subscribe(
      "US100",
      "MINUTE_5" as Resolution,
      () => {},
    );
    await settle();
    // The connection drops; the hub diagnoses, finds the pair is collected, and
    // retries — which must cost a second ticket, not repeat the first.
    spy.opened[0].onclose?.({ code: 1006, reason: "" });
    await new Promise((resolve) => setTimeout(resolve, 900));

    expect(spy.urls).toHaveLength(2);
    expect(spy.urls[0]).toContain("ticket=ticket-1");
    expect(spy.urls[1]).toContain("ticket=ticket-2");
  });
});

describe("archive.indicatorCatalogue", () => {
  it("maps every field a picker needs, snake_case to camelCase", async () => {
    server.use(
      http.get(`${HTTP_BASE}/indicators`, () =>
        HttpResponse.json({
          algorithm_version: 1,
          indicators: [
            {
              id: "ema",
              name: "Exponential Moving Average",
              aliases: [],
              group: "averages",
              output: "lines",
              params: [{ name: "period", type: "int", default: 20, min: 2, max: 5000 }],
              lines: [{ key: "ema", label: "EMA {period}" }],
              render: {
                pane: "price",
                style: "line",
                scale: "price",
                autoscale: true,
                range: null,
                levels: [],
              },
              warmup_kind: "decay",
            },
          ],
        }),
      ),
    );

    const catalogue = await source().indicatorCatalogue(signal());

    expect(catalogue.algorithmVersion).toBe(1);
    const [entry] = catalogue.indicators;
    expect(entry).toMatchObject({
      id: "ema",
      warmupKind: "decay",
      render: { pane: "price", autoscale: true },
    });
  });
});

describe("archive.computeIndicators", () => {
  it("sends the range in ISO and the resolved id/params, answers in epoch seconds", async () => {
    server.use(
      http.post(`${HTTP_BASE}/indicators/US100`, async ({ request }) => {
        const body = (await request.json()) as {
          resolution: string;
          from: string;
          to: string;
          specs: Array<{ id: string; params: Record<string, number> }>;
        };
        expect(body.resolution).toBe("MINUTE_5");
        expect(body.from).toBe("2026-08-07T14:00:00.000Z");
        expect(body.to).toBe("2026-08-07T15:00:00.000Z");
        expect(body.specs).toEqual([{ id: "ema", params: { period: 20 } }]);

        return HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE_5",
          price_side: "bid",
          derived: false,
          algorithm_version: 1,
          times: ["2026-08-07T14:35:00Z"],
          warmup_from: "2026-08-07T10:00:00Z",
          uncovered: [],
          results: [
            {
              id: "ema",
              params: { period: 20 },
              warmup_bars: 210,
              settled: true,
              lines: { ema: [21042.5] },
              markers: null,
              zones: null,
              levels: null,
            },
          ],
        });
      }),
    );

    const result = await source().computeIndicators(
      "US100",
      "MINUTE_5" as Resolution,
      Date.parse("2026-08-07T14:00:00Z") / 1000,
      Date.parse("2026-08-07T15:00:00Z") / 1000,
      [{ key: "i1", id: "ema", params: { period: 20 }, color: null }],
      signal(),
    );

    expect(result.times).toEqual([Date.parse("2026-08-07T14:35:00Z") / 1000]);
    const [emaResult] = result.results;
    expect(emaResult.settled).toBe(true);
    expect(emaResult.warmupBars).toBe(210);
    expect(emaResult.lines).toEqual({ ema: [21042.5] });
  });

  it("keeps the instance key and the chosen colour off the wire", async () => {
    // Both are the terminal's own vocabulary: the archive computes an indicator, it does
    // not draw one, and nothing on `IndicatorSpecIn` would carry either.
    let sentSpecs: unknown;
    server.use(
      http.post(`${HTTP_BASE}/indicators/US100`, async ({ request }) => {
        sentSpecs = ((await request.json()) as { specs: unknown }).specs;
        return HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE_5",
          price_side: "bid",
          derived: false,
          algorithm_version: 1,
          times: [],
          warmup_from: null,
          uncovered: [],
          results: [],
        });
      }),
    );

    await source().computeIndicators(
      "US100",
      "MINUTE_5" as Resolution,
      Date.parse("2026-08-07T14:00:00Z") / 1000,
      Date.parse("2026-08-07T15:00:00Z") / 1000,
      [
        { key: "i1", id: "ema", params: { period: 20 }, color: "--color-accent" },
        { key: "i2", id: "ema", params: { period: 50 }, color: null },
      ],
      signal(),
    );

    expect(sentSpecs).toEqual([
      { id: "ema", params: { period: 20 } },
      { id: "ema", params: { period: 50 } },
    ]);
  });

  it("maps zones and markers to epoch seconds, null to null", async () => {
    server.use(
      http.post(`${HTTP_BASE}/indicators/US100`, () =>
        HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          price_side: "bid",
          derived: false,
          algorithm_version: 1,
          times: [],
          warmup_from: null,
          uncovered: [],
          results: [
            {
              id: "range_gap",
              params: {},
              warmup_bars: null,
              settled: true,
              lines: null,
              markers: null,
              zones: [
                {
                  from: "2026-08-07T14:00:00Z",
                  to: null,
                  top: 21100,
                  bottom: 21080,
                  direction: "bullish",
                  touched_at: null,
                  filled_at: null,
                },
              ],
              levels: null,
            },
          ],
        }),
      ),
    );

    const result = await source().computeIndicators(
      "US100",
      "MINUTE" as Resolution,
      0,
      1,
      [{ key: "range_gap", id: "range_gap", params: {}, color: null }],
      signal(),
    );

    const [gapResult] = result.results;
    expect(gapResult.zones).toEqual([
      {
        from: Date.parse("2026-08-07T14:00:00Z") / 1000,
        to: null,
        top: 21100,
        bottom: 21080,
        direction: "bullish",
        touchedAt: null,
        filledAt: null,
      },
    ]);
  });

  it("refuses by name when the archive names a refusal", async () => {
    server.use(
      http.post(`${HTTP_BASE}/indicators/US100`, () =>
        HttpResponse.json({ detail: "unknown indicator: 'not-real'" }, { status: 422 }),
      ),
    );

    await expect(
      source().computeIndicators(
        "US100",
        "MINUTE" as Resolution,
        0,
        1,
        [{ key: "not-real", id: "not-real", params: {}, color: null }],
        signal(),
      ),
    ).rejects.toMatchObject({ kind: "refused" });
  });
});
