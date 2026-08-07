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
  return createGatewaySource(HTTP_BASE);
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

  it("maps a FastAPI validation error to a readable message, not a raw shape", async () => {
    server.use(
      http.get(`${HTTP_BASE}/instruments/search`, () =>
        HttpResponse.json(
          { detail: [{ loc: ["query", "q"], msg: "query is too short", type: "value_error" }] },
          { status: 422 },
        ),
      ),
    );

    const call = source().searchInstruments("g", new AbortController().signal);
    await expect(call).rejects.toBeInstanceOf(MarketDataError);
    await expect(call).rejects.toMatchObject({ message: "query is too short" });
  });

  // The whole point of leaving the catalogue with the gateway: an archive that
  // is down takes the candles with it and nothing else (terminal-market-data
  // spec, "Jedno ze źródeł nie odpowiada"). This is that claim at the adapter
  // level — the search asks the gateway and nobody else.
  it("asks the gateway and only the gateway", async () => {
    const seen: string[] = [];
    server.use(
      http.get(`${HTTP_BASE}/instruments/search`, ({ request }) => {
        seen.push(new URL(request.url).host);
        return HttpResponse.json([]);
      }),
    );

    await source().searchInstruments("gold", new AbortController().signal);
    expect(seen).toEqual(["gateway.test"]);
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

  it("maps a network failure to unreachable, not a raw fetch error", async () => {
    server.use(http.get(`${HTTP_BASE}/instruments`, () => HttpResponse.error()));

    await expect(
      source().listInstruments(new AbortController().signal),
    ).rejects.toMatchObject({ kind: "unreachable", message: "capital-gateway is not reachable" });
  });
});

describe("gatewaySource.ping", () => {
  it("resolves when /capabilities answers", async () => {
    server.use(
      http.get(`${HTTP_BASE}/capabilities`, () => HttpResponse.json({ provider: "capital.com" })),
    );
    await expect(source().ping(new AbortController().signal)).resolves.toBeUndefined();
  });

  it("rejects with unreachable when the gateway can't be reached", async () => {
    server.use(http.get(`${HTTP_BASE}/capabilities`, () => HttpResponse.error()));
    await expect(source().ping(new AbortController().signal)).rejects.toMatchObject({
      kind: "unreachable",
    });
  });
});
