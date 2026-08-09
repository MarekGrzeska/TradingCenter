import { describe, expect, it, vi } from "vitest";
import {
  archivedInstrumentSource,
  assetClassSource,
  instrumentInClassSource,
} from "./autocompleteSources";
import type { ArchiveAdmin, InstrumentSource } from "../data/source";
import type { AssetClass, Instrument, TrackedPair } from "../data/types";

function fakeInstrumentSource(overrides: Partial<InstrumentSource> = {}): InstrumentSource {
  return {
    id: "gateway",
    label: "capital-gateway",
    whenUnreachable: "instrument search is unavailable",
    ping: vi.fn(async () => {}),
    searchInstruments: vi.fn(async () => []),
    listInstruments: vi.fn(async () => ({ instruments: [], count: 0, truncated: false })),
    listAssetClasses: vi.fn(async () => []),
    ...overrides,
  };
}

function fakeArchiveAdmin(overrides: Partial<ArchiveAdmin> = {}): ArchiveAdmin {
  return {
    listPairs: vi.fn(async () => []),
    trackPairs: vi.fn(async () => ({ results: [], jobId: null })),
    deletePair: vi.fn(async () => ({
      symbol: "",
      resolution: "MINUTE" as const,
      deletedAt: 0,
      candlesRemoved: 0,
      removedFrom: null,
      removedTo: null,
    })),
    coverage: vi.fn(async () => ({
      symbol: "",
      resolution: "MINUTE" as const,
      ranges: [],
      earliestReachable: null,
    })),
    listDeletions: vi.fn(async () => []),
    estimateJob: vi.fn(async () => ({ pairs: [], totalEstimatedCandles: 0, totalEstimatedBytes: 0 })),
    listJobs: vi.fn(async () => []),
    readJob: vi.fn(),
    retryJob: vi.fn(),
    ...overrides,
  };
}

function instrument(symbol: string, assetClass: AssetClass): Instrument {
  return { symbol, name: symbol, assetClass, tradeable: true, bid: null, ask: null };
}

function trackedPair(symbol: string, resolution: TrackedPair["resolution"]): TrackedPair {
  return {
    symbol,
    resolution,
    addedAt: 0,
    collectFrom: 0,
    earliestCandle: null,
    latestCandle: null,
    collection: "collecting",
  };
}

const signal = () => new AbortController().signal;

describe("assetClassSource", () => {
  it("returns every class on an empty query", async () => {
    const gateway = fakeInstrumentSource({
      listAssetClasses: vi.fn(async () => ["CRYPTO", "INDICES", "SHARES"] as AssetClass[]),
    });
    const page = await assetClassSource(gateway)("", signal());
    expect(page.options).toEqual(["CRYPTO", "INDICES", "SHARES"]);
  });

  it("filters locally by substring, case-insensitively", async () => {
    const gateway = fakeInstrumentSource({
      listAssetClasses: vi.fn(async () => ["CRYPTO", "INDICES", "SHARES"] as AssetClass[]),
    });
    const page = await assetClassSource(gateway)("ind", signal());
    expect(page.options).toEqual(["INDICES"]);
  });

  it("never reports truncation — the whole set is always read", async () => {
    const gateway = fakeInstrumentSource({
      listAssetClasses: vi.fn(async () => ["CRYPTO"] as AssetClass[]),
    });
    const page = await assetClassSource(gateway)("", signal());
    expect(page.truncated).toBeUndefined();
  });
});

describe("instrumentInClassSource", () => {
  it("enumerates the class on an empty query, carrying the gateway's truncated flag", async () => {
    const listInstruments = vi.fn(async () => ({
      instruments: [instrument("BTCUSD", "CRYPTO")],
      count: 1500,
      truncated: true,
    }));
    const gateway = fakeInstrumentSource({ listInstruments });
    const page = await instrumentInClassSource(gateway, "CRYPTO")("", signal());

    expect(listInstruments).toHaveBeenCalledWith(signal(), "CRYPTO");
    expect(page.options).toEqual([instrument("BTCUSD", "CRYPTO")]);
    expect(page.truncated).toBe(true);
  });

  it("searches within the class once a query is typed, and never truncates", async () => {
    const searchInstruments = vi.fn(async () => [instrument("BTCUSD", "CRYPTO")]);
    const gateway = fakeInstrumentSource({ searchInstruments });
    const page = await instrumentInClassSource(gateway, "CRYPTO")("btc", signal());

    expect(searchInstruments).toHaveBeenCalledWith("btc", signal(), "CRYPTO");
    expect(gateway.listInstruments).not.toHaveBeenCalled();
    expect(page.truncated).toBeUndefined();
  });
});

describe("archivedInstrumentSource", () => {
  it("groups pairs by symbol, carrying every resolution collected", async () => {
    const archive = fakeArchiveAdmin({
      listPairs: vi.fn(async () => [
        trackedPair("US100", "MINUTE"),
        trackedPair("US100", "HOUR"),
        trackedPair("GOLD", "DAY"),
      ]),
    });
    const page = await archivedInstrumentSource(archive)("", signal());

    expect(page.options).toEqual([
      { symbol: "GOLD", resolutions: ["DAY"] },
      { symbol: "US100", resolutions: ["MINUTE", "HOUR"] },
    ]);
  });

  it("filters locally by symbol, case-insensitively", async () => {
    const archive = fakeArchiveAdmin({
      listPairs: vi.fn(async () => [trackedPair("US100", "MINUTE"), trackedPair("GOLD", "DAY")]),
    });
    const page = await archivedInstrumentSource(archive)("us1", signal());
    expect(page.options).toEqual([{ symbol: "US100", resolutions: ["MINUTE"] }]);
  });

  it("reads an empty archive as no options, not a failure", async () => {
    const archive = fakeArchiveAdmin({ listPairs: vi.fn(async () => []) });
    const page = await archivedInstrumentSource(archive)("", signal());
    expect(page.options).toEqual([]);
  });
});
