import { afterEach, describe, expect, it, vi } from "vitest";
import { createPolymarketApi } from "./api";
import { ArchiveError } from "../data/http";

const EVENT = {
  id: 1,
  provider_event_id: "evt-1",
  slug: "will-it-happen",
  title: "Will it happen",
  url: "https://polymarket.com/event/will-it-happen",
  group: "Politics",
  tracked_at: "2026-08-30T10:00:00Z",
  collection: { state: "collecting", last_sample_at: "2026-08-31T09:00:00Z", reason: null },
  markets: [
    {
      id: 10,
      question: "Will it happen?",
      label: null,
      neg_risk: true,
      resolved_outcome: null,
      outcomes: [
        {
          id: 100,
          name: "Yes",
          position: 0,
          price: 0.62,
          price_at: "2026-08-31T09:00:00Z",
          last_trade: 0.61,
          collected_from: "2026-08-24T09:00:00Z",
        },
        {
          id: 101,
          name: "No",
          position: 1,
          price: null,
          price_at: null,
          last_trade: null,
          collected_from: null,
        },
      ],
    },
  ],
};

function answering(status: number, body: unknown) {
  return vi.fn(async () =>
    status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("reading the observations", () => {
  it("turns the wire shape into dates and keeps an uncollected price null", async () => {
    vi.stubGlobal("fetch", answering(200, [EVENT]));

    const [event] = await createPolymarketApi("/api").listEvents(new AbortController().signal);

    expect(event.providerEventId).toBe("evt-1");
    expect(event.group).toBe("Politics");
    expect(event.collection.lastSampleAt).toEqual(new Date("2026-08-31T09:00:00Z"));
    expect(event.markets[0].negRisk).toBe(true);
    expect(event.markets[0].outcomes[0].price).toBe(0.62);
    // Not the epoch, which is what `new Date(null)` would have made of it.
    expect(event.markets[0].outcomes[1].priceAt).toBeNull();
  });
});

describe("what a refusal is", () => {
  it("names the tracking ceiling as a refusal, carrying the archive's own reason", async () => {
    vi.stubGlobal("fetch", answering(409, { detail: "already observing 40 events" }));

    const failure = await createPolymarketApi("/api")
      .trackEvent("some-slug", new AbortController().signal)
      .catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(ArchiveError);
    expect((failure as ArchiveError).kind).toBe("refused");
    expect((failure as ArchiveError).message).toBe("already observing 40 events");
  });

  it("tells an archive that is down from one that said no", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const failure = await createPolymarketApi("/api")
      .listEvents(new AbortController().signal)
      .catch((cause: unknown) => cause);

    expect((failure as ArchiveError).kind).toBe("unreachable");
  });
});

describe("removing an observation", () => {
  it("reads no body from the 204 the archive answers with", async () => {
    const fetching = answering(204, null);
    vi.stubGlobal("fetch", fetching);

    await expect(
      createPolymarketApi("/api").removeEvent("evt-1", new AbortController().signal),
    ).resolves.toBeUndefined();
    expect(fetching).toHaveBeenCalledWith(
      "/api/events/evt-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
