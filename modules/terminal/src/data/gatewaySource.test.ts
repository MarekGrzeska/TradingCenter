import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createGatewaySource } from "./gatewaySource";
import { MarketDataError } from "./types";

const HTTP_BASE = "http://gateway.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function source() {
  return createGatewaySource(HTTP_BASE, "ws://gateway.test/ws");
}

describe("gatewaySource.searchInstruments", () => {
  it("maps snake_case instruments to the terminal's own shape", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/search`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("q")).toBe("gold");
        return HttpResponse.json([
          {
            symbol: "GOLD",
            name: "Gold",
            asset_class: "COMMODITIES",
            tradeable: true,
            bid: 2400.1,
            ask: 2400.4,
          },
        ]);
      }),
    );

    const result = await source().searchInstruments("gold", new AbortController().signal);
    expect(result).toEqual([
      {
        symbol: "GOLD",
        name: "Gold",
        assetClass: "COMMODITIES",
        tradeable: true,
        bid: 2400.1,
        ask: 2400.4,
      },
    ]);
  });
});

describe("gatewaySource.listInstruments", () => {
  it("carries the truncated flag through", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments`, () =>
        HttpResponse.json({
          instruments: [],
          count: 300,
          truncated: true,
          nodes_visited: 300,
        }),
      ),
    );

    const page = await source().listInstruments(new AbortController().signal);
    expect(page).toEqual({ instruments: [], count: 300, truncated: true });
  });
});

describe("gatewaySource.history", () => {
  it("converts ISO timestamps to epoch seconds and marks bars settled", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/US100/history`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("resolution")).toBe("MINUTE_5");
        expect(url.searchParams.get("bars")).toBe("2");
        return HttpResponse.json({
          candles: [
            { ts: "2026-08-07T14:35:00Z", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
            { ts: "2026-08-07T14:40:00Z", open: 1.5, high: 2, low: 1, close: 1.8, volume: null },
          ],
        });
      }),
    );

    const bars = await source().history(
      { symbol: "US100", resolution: "MINUTE_5", count: 2 },
      new AbortController().signal,
    );
    expect(bars).toEqual([
      { time: 1786113300, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, forming: false },
      { time: 1786113600, open: 1.5, high: 2, low: 1, close: 1.8, volume: null, forming: false },
    ]);
  });

  it("drops a candle missing an OHLC field instead of faking a zero", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/US100/history`, () =>
        HttpResponse.json({
          candles: [
            { ts: "2026-08-07T14:35:00Z", open: null, high: null, low: null, close: null, volume: null },
            { ts: "2026-08-07T14:40:00Z", open: 1, high: 1, low: 1, close: 1, volume: null },
          ],
        }),
      ),
    );

    const bars = await source().history(
      { symbol: "US100", resolution: "MINUTE_5", count: 2 },
      new AbortController().signal,
    );
    expect(bars).toHaveLength(1);
    expect(bars[0].time).toBe(1786113600);
  });

  it("maps a 404 to a not-found MarketDataError naming the symbol", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/NOPE/history`, () =>
        HttpResponse.json({ detail: "unknown instrument 'NOPE'" }, { status: 404 }),
      ),
    );

    const call = source().history(
      { symbol: "NOPE", resolution: "MINUTE_5", count: 10 },
      new AbortController().signal,
    );
    await expect(call).rejects.toBeInstanceOf(MarketDataError);
    await expect(call).rejects.toMatchObject({
      kind: "not-found",
      message: "unknown instrument 'NOPE'",
    });
  });

  it("maps a FastAPI 422 validation error to unsupported-resolution", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/US100/history`, () =>
        HttpResponse.json(
          { detail: [{ loc: ["query", "resolution"], msg: "invalid enum value", type: "enum" }] },
          { status: 422 },
        ),
      ),
    );

    await expect(
      source().history(
        // @ts-expect-error deliberately invalid — exercising the gateway's own rejection
        { symbol: "US100", resolution: "NOT_A_RESOLUTION", count: 10 },
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "unsupported-resolution" });
  });

  it("maps a network failure to unreachable, not a raw fetch error", async () => {
    server.use(http.get(`${HTTP_BASE}/instruments/US100/history`, () => HttpResponse.error()));

    await expect(
      source().history(
        { symbol: "US100", resolution: "MINUTE_5", count: 10 },
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "unreachable" });
  });
});

describe("gatewaySource.ping", () => {
  it("resolves when /capabilities answers", async () => {
    server.use(http.get(`${HTTP_BASE}/capabilities`, () => HttpResponse.json({ provider: "capital.com" })));
    await expect(source().ping(new AbortController().signal)).resolves.toBeUndefined();
  });

  it("rejects with unreachable when the gateway can't be reached", async () => {
    server.use(http.get(`${HTTP_BASE}/capabilities`, () => HttpResponse.error()));
    await expect(source().ping(new AbortController().signal)).rejects.toMatchObject({
      kind: "unreachable",
    });
  });
});
