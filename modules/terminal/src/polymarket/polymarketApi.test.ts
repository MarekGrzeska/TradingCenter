import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createPolymarketApi } from "./polymarketApi";

/**
 * The wire↔domain seam, the whole reason that file exists: everything past it works in `Date`s, camelCase and
 * probabilities on 0..1, and nothing past it knows what the module's JSON looks like.
 */

const HTTP_BASE = "http://polymarket.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function api() {
  return createPolymarketApi(HTTP_BASE);
}

function signal() {
  return new AbortController().signal;
}

const OUTCOME = {
  id: 7,
  name: "Yes",
  position: 0,
  price: 0.62,
  price_at: "2026-08-22T10:00:00Z",
  last_trade: 0.61,
  collected_from: "2026-05-24T00:00:00Z",
};

const EVENT = {
  id: 1,
  provider_event_id: "0xabc",
  slug: "fed-cuts-in-march",
  title: "Fed cuts in March",
  url: "https://polymarket.com/event/fed-cuts-in-march",
  group: "macro",
  tracked_at: "2026-08-22T09:00:00Z",
  collection: { state: "collecting", last_sample_at: "2026-08-22T10:00:00Z", reason: null },
  markets: [
    {
      id: 4,
      question: "Will the Fed cut in March?",
      label: null,
      neg_risk: false,
      resolved_outcome: null,
      outcomes: [OUTCOME, { ...OUTCOME, id: 8, name: "No", position: 1, price: 0.38 }],
    },
  ],
};

describe("listEvents", () => {
  it("maps the module's shape to the terminal's, moments included", async () => {
    server.use(http.get(`${HTTP_BASE}/events`, () => HttpResponse.json([EVENT])));

    const [event] = await api().listEvents(signal());

    expect(event.providerEventId).toBe("0xabc");
    expect(event.title).toBe("Fed cuts in March");
    expect(event.trackedAt).toEqual(new Date("2026-08-22T09:00:00Z"));
    expect(event.collection.state).toBe("collecting");
    expect(event.markets[0].outcomes[0]).toEqual({
      id: 7,
      name: "Yes",
      price: 0.62,
      priceAt: new Date("2026-08-22T10:00:00Z"),
      lastTrade: 0.61,
      collectedFrom: new Date("2026-05-24T00:00:00Z"),
    });
  });

  it("keeps a probability on 0..1 rather than turning it into a percentage", async () => {
    server.use(http.get(`${HTTP_BASE}/events`, () => HttpResponse.json([EVENT])));

    const [event] = await api().listEvents(signal());

    expect(event.markets[0].outcomes[0].price).toBe(0.62);
  });

  it("leaves an absent moment absent rather than making it the epoch", async () => {
    server.use(
      http.get(`${HTTP_BASE}/events`, () =>
        HttpResponse.json([
          {
            ...EVENT,
            tracked_at: null,
            markets: [
              {
                ...EVENT.markets[0],
                outcomes: [{ ...OUTCOME, price: null, price_at: null, collected_from: null }],
              },
            ],
          },
        ]),
      ),
    );

    const [event] = await api().listEvents(signal());

    expect(event.trackedAt).toBeNull();
    expect(event.markets[0].outcomes[0].priceAt).toBeNull();
    expect(event.markets[0].outcomes[0].price).toBeNull();
  });

  it("keeps every outcome of a multi-outcome market, in the provider's order", async () => {
    // The order is what pairs an outcome with its token, and the shape is the point: the
    // module that this one replaces stored a sample only for `Yes`/`No` markets.
    server.use(
      http.get(`${HTTP_BASE}/events`, () =>
        HttpResponse.json([
          {
            ...EVENT,
            markets: [
              {
                ...EVENT.markets[0],
                neg_risk: true,
                outcomes: [
                  { ...OUTCOME, id: 11, name: "Newsom", position: 0, price: 0.31 },
                  { ...OUTCOME, id: 12, name: "Harris", position: 1, price: 0.19 },
                  { ...OUTCOME, id: 13, name: "Someone else", position: 2, price: 0.5 },
                ],
              },
            ],
          },
        ]),
      ),
    );

    const [event] = await api().listEvents(signal());

    expect(event.markets[0].negRisk).toBe(true);
    expect(event.markets[0].outcomes.map((o) => o.name)).toEqual([
      "Newsom",
      "Harris",
      "Someone else",
    ]);
  });

  it("can ask for the ended events to be left out, which the module includes by default", async () => {
    const asked: string[] = [];
    server.use(
      http.get(`${HTTP_BASE}/events`, ({ request }) => {
        asked.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
    );

    await api().listEvents(signal(), { includeEnded: false });

    // A falsy check made `false` unsendable — the one value worth passing, since the module
    // defaults this to true.
    expect(asked).toEqual(["?include_ended=false"]);
  });

  it("asks for one group only when one was named", async () => {
    const asked: string[] = [];
    server.use(
      http.get(`${HTTP_BASE}/events`, ({ request }) => {
        asked.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
    );

    await api().listEvents(signal());
    await api().listEvents(signal(), { groupId: 3 });

    expect(asked).toEqual(["", "?group_id=3"]);
  });
});

describe("snapshot", () => {
  it("reads every tracked outcome's price in one request", async () => {
    let calls = 0;
    server.use(
      http.get(`${HTTP_BASE}/snapshot`, () => {
        calls += 1;
        return HttpResponse.json({
          entries: [
            {
              event_id: 1,
              event_slug: "fed-cuts-in-march",
              market_id: 4,
              market_label: null,
              outcome_id: 7,
              outcome_name: "Yes",
              price: 0.62,
              price_at: "2026-08-22T10:00:00Z",
            },
          ],
        });
      }),
    );

    const entries = await api().snapshot(signal());

    expect(calls).toBe(1);
    expect(entries).toEqual([
      {
        eventId: 1,
        eventSlug: "fed-cuts-in-march",
        marketId: 4,
        marketLabel: null,
        outcomeId: 7,
        outcomeName: "Yes",
        price: 0.62,
        priceAt: new Date("2026-08-22T10:00:00Z"),
      },
    ]);
  });
});

describe("changes", () => {
  it("carries a window with no coverage as its reason, never as a zero", async () => {
    server.use(
      http.get(`${HTTP_BASE}/events/0xabc/changes`, () =>
        HttpResponse.json({
          event_id: 1,
          outcomes: [
            {
              outcome_id: 7,
              name: "Yes",
              price: 0.62,
              windows: [
                {
                  window: "24h",
                  change: 0.021,
                  unavailable: null,
                  baseline_at: "2026-08-21T09:58:00Z",
                },
                {
                  window: "7d",
                  change: null,
                  unavailable: "collected history reaches back 2 days",
                  baseline_at: null,
                },
              ],
            },
          ],
        }),
      ),
    );

    const changes = await api().changes("0xabc", signal());
    const [moved, uncovered] = changes.outcomes[0].windows;

    expect(moved).toEqual({
      window: "24h",
      change: 0.021,
      unavailable: null,
      baselineAt: new Date("2026-08-21T09:58:00Z"),
    });
    expect(uncovered.change).toBeNull();
    expect(uncovered.unavailable).toBe("collected history reaches back 2 days");
  });
});

describe("history", () => {
  it("carries the collected boundary, which is not the first point", async () => {
    server.use(
      http.get(`${HTTP_BASE}/outcomes/7/history`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("since")).toBe("2026-08-01T00:00:00.000Z");
        return HttpResponse.json({
          outcome_id: 7,
          points: [
            { at: "2026-08-20T00:00:00Z", price: 0.5, last_trade: null },
            { at: "2026-08-21T00:00:00Z", price: 0.55, last_trade: 0.54 },
          ],
          collected_from: "2026-08-19T12:00:00Z",
          collected_to: "2026-08-22T10:00:00Z",
        });
      }),
    );

    const history = await api().history(7, signal(), { since: new Date("2026-08-01T00:00:00Z") });

    expect(history.points).toHaveLength(2);
    expect(history.points[0].at).toEqual(new Date("2026-08-20T00:00:00Z"));
    expect(history.collectedFrom).toEqual(new Date("2026-08-19T12:00:00Z"));
  });
});

describe("tracking", () => {
  it("says an event was already tracked rather than reporting a second observation", async () => {
    server.use(
      http.post(`${HTTP_BASE}/events`, async ({ request }) => {
        expect(await request.json()).toEqual({ reference: "https://polymarket.com/event/x" });
        return HttpResponse.json({ event: EVENT, already_tracked: true });
      }),
    );

    const result = await api().trackEvent("https://polymarket.com/event/x", signal());

    expect(result.alreadyTracked).toBe(true);
    expect(result.event.slug).toBe("fed-cuts-in-march");
  });

  it("sends the group only when one was named", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/events`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ event: EVENT, already_tracked: false });
      }),
    );

    await api().trackEvent("slug", signal(), "macro");

    expect(body).toEqual({ reference: "slug", group: "macro" });
  });

  it("removes an observation and reads nothing back about it", async () => {
    let asked = "";
    server.use(
      http.delete(`${HTTP_BASE}/events/0xabc`, ({ request }) => {
        asked = new URL(request.url).pathname;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await api().removeEvent("0xabc", signal());

    // 204 and nothing parsed: what a module could answer about a thing that no longer
    // exists is a shape somebody would be tempted to read.
    expect(asked).toBe("/events/0xabc");
  });

  it("reports the ceiling as a refusal rather than as a failure", async () => {
    server.use(
      http.post(`${HTTP_BASE}/events`, () =>
        HttpResponse.json({ detail: "50 events are already tracked; end one first" }, { status: 409 }),
      ),
    );

    await expect(api().trackEvent("slug", signal())).rejects.toMatchObject({
      kind: "refused",
      message: "50 events are already tracked; end one first",
    });
  });
});

describe("groups", () => {
  it("reads a 204 as success rather than choking on an empty body", async () => {
    // `Response.json()` on an empty body throws a SyntaxError, which would surface as a
    // broken screen where the module in fact did what was asked.
    server.use(
      http.delete(`${HTTP_BASE}/groups/3`, () => new Response(null, { status: 204 })),
      http.put(`${HTTP_BASE}/events/1/group`, () => new Response(null, { status: 204 })),
    );

    await expect(api().deleteGroup(3, signal())).resolves.toBeUndefined();
    await expect(api().assignGroup(1, null, signal())).resolves.toBeUndefined();
  });

  it("sends a null group id to take an event out of every group", async () => {
    let body: unknown;
    server.use(
      http.put(`${HTTP_BASE}/events/1/group`, async ({ request }) => {
        body = await request.json();
        return new Response(null, { status: 204 });
      }),
    );

    await api().assignGroup(1, null, signal());

    expect(body).toEqual({ group_id: null });
  });
});

describe("refusals", () => {
  it("tells a caller with no business here apart from a module that did not answer", async () => {
    // The distinction the platform cannot make: Easy Auth admits an application, and this module then decides
    // which surface it may reach. One is a permission to be granted; the other is an outage.
    server.use(
      http.get(`${HTTP_BASE}/events`, () =>
        HttpResponse.json({ detail: "caller may not reach the REST contract" }, { status: 403 }),
      ),
    );

    await expect(api().listEvents(signal())).rejects.toMatchObject({ kind: "refused" });

    server.resetHandlers();
    server.use(
      http.get(`${HTTP_BASE}/events`, () => {
        throw new TypeError("failed to fetch");
      }),
    );

    const failure = await api()
      .listEvents(signal())
      .catch((cause: unknown) => cause);
    expect(failure).toBeInstanceOf(MarketDataError);
    expect((failure as MarketDataError).kind).toBe("unreachable");
  });

  it("calls the provider's own failure retryable, and the module's not", async () => {
    server.use(
      http.get(`${HTTP_BASE}/events/0xabc/changes`, () =>
        HttpResponse.json({ detail: "Polymarket refused" }, { status: 502 }),
      ),
    );

    await expect(api().changes("0xabc", signal())).rejects.toMatchObject({ kind: "upstream" });
  });
});
