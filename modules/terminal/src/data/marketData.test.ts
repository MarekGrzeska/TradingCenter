import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { marketData } from "./marketData";

/**
 * The composition, from the outside — the only place the two back ends are one
 * thing. Everything here is about a view's point of view: it calls one object,
 * and the split behind it is neither visible nor its problem
 * (terminal-market-data spec, "Świece i instrumenty idą z różnych miejsc").
 *
 * The default addresses put both behind the page origin, which is what the dev
 * proxy does and what these handlers stand in for.
 */

const ORIGIN = "http://localhost:3000";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function signal() {
  return new AbortController().signal;
}

describe("the composed source", () => {
  it("sends candles to the archive and instruments to the gateway", async () => {
    const asked: string[] = [];
    server.use(
      http.get(`${ORIGIN}/archive-api/candles/US100`, ({ request }) => {
        asked.push(new URL(request.url).pathname);
        return HttpResponse.json({
          symbol: "US100",
          resolution: "MINUTE",
          price_side: "bid",
          derived: false,
          candles: [],
          uncovered: [],
        });
      }),
      http.get(`${ORIGIN}/archive-api/instruments/search`, ({ request }) => {
        asked.push(new URL(request.url).pathname);
        return HttpResponse.json([]);
      }),
    );

    await marketData.history({ symbol: "US100", resolution: "MINUTE", from: 0, to: 1 }, signal());
    await marketData.searchInstruments("us", signal());

    expect(asked).toEqual(["/archive-api/candles/US100", "/archive-api/instruments/search"]);
  });

  it("keeps the instrument search working while the archive's own data path is down", async () => {
    // market-data now proxies the catalogue too (provision-azure-platform,
    // design.md — capital-gateway is not public), so the two no longer fail
    // fully independently: a `market-data` process outage takes both down.
    // What still separates cleanly is *within* market-data — its
    // database-backed routes (candles, health) and its gateway-proxy routes
    // (search, asset classes) are handled independently, so one failing does
    // not take the other with it. That is what this proves.
    server.use(
      http.get(`${ORIGIN}/archive-api/candles/US100`, () => HttpResponse.error()),
      http.get(`${ORIGIN}/archive-api/health`, () => HttpResponse.error()),
      http.get(`${ORIGIN}/archive-api/instruments/search`, () =>
        HttpResponse.json([
          {
            symbol: "US100",
            name: "US 100",
            asset_class: "INDICES",
            tradeable: true,
            bid: 1,
            ask: 2,
          },
        ]),
      ),
      http.get(`${ORIGIN}/archive-api/asset-classes`, () => HttpResponse.json(["INDICES"])),
    );

    await expect(
      marketData.history({ symbol: "US100", resolution: "MINUTE", from: 0, to: 1 }, signal()),
    ).rejects.toMatchObject({ kind: "unreachable" });

    const found = await marketData.searchInstruments("us", signal());
    expect(found.map((instrument) => instrument.symbol)).toEqual(["US100"]);

    // And the shell can say which of the two is down rather than declaring the
    // whole terminal offline.
    const [archivePart, gatewayPart] = marketData.parts;
    await expect(archivePart.ping(signal())).rejects.toMatchObject({ kind: "unreachable" });
    await expect(gatewayPart.ping(signal())).resolves.toBeUndefined();
  });

  it("names both back ends, and what each one's absence costs", () => {
    expect(marketData.parts.map((part) => part.label)).toEqual([
      "market-data",
      "capital-gateway",
    ]);
    for (const part of marketData.parts) {
      expect(part.whenUnreachable).not.toBe("");
    }
  });
});
