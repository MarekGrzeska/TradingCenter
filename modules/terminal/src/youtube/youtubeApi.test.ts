import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createYoutubeApi } from "./youtubeApi";

/**
 * The wire↔domain seam: everything past it works in `Date`s and camelCase, and nothing past it knows what the module's JSON
 * looks like. The two things worth a test are the ones that fail quietly — a reading that is `null` staying `null`, and a
 * request body missing what the contract says is required.
 */

const BASE = "http://youtube.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const signal = () => new AbortController().signal;

const READING = {
  profile: "market",
  summary_pl: "Autor uważa, że złoto wzrośnie.",
  key_points: ["banki kupują"],
  instruments: [{ name: "Gold", epic: "GOLD", sentiment: "bullish", conviction: 4, horizon: "swing" }],
  predictions: [{ instrument: "Gold", claim: "3000 USD", level: 3000, by: "2026-12-31" }],
  topics: ["złoto"],
  impact_score: 6,
  model: "sim",
  analysed_at: "2026-09-27T10:05:00Z",
  simulated: true,
};

const FILM = {
  video_id: "simfilm0001",
  url: "https://www.youtube.com/watch?v=simfilm0001",
  title: "Złoto",
  channel_id: "UC1",
  channel_title: "Sim Złoto PL",
  published_at: "2026-09-27T08:30:00Z",
  duration_seconds: 1500,
  live_status: "none",
  state: "quiet",
  skip_reason: null,
  origins: ["channel:UC1"],
  attempts: 0,
  next_attempt_at: null,
  notified_at: null,
  discovered_at: "2026-09-27T09:00:00Z",
  simulated: true,
  reading: READING,
};

describe("recentFilms", () => {
  it("maps a read film with its moments, and leaves an unread one's reading null", async () => {
    server.use(
      http.get(`${BASE}/videos`, () =>
        HttpResponse.json({
          videos: [FILM, { ...FILM, video_id: "simfilm0008", reading: null, state: "no_transcript", attempts: 2 }],
          count: 2,
          window_from: "2026-09-26T10:00:00Z",
          window_to: "2026-09-27T10:00:00Z",
        }),
      ),
    );

    const page = await createYoutubeApi(BASE).recentFilms(24, signal());

    const [read, unread] = page.films;
    expect(read.publishedAt).toEqual(new Date("2026-09-27T08:30:00Z"));
    expect(read.simulated).toBe(true);
    expect(read.reading?.summary).toBe("Autor uważa, że złoto wzrośnie.");
    expect(read.reading?.instruments[0]).toEqual({
      name: "Gold",
      epic: "GOLD",
      sentiment: "bullish",
      conviction: 4,
      horizon: "swing",
    });
    expect(read.reading?.analysedAt).toEqual(new Date("2026-09-27T10:05:00Z"));
    // Not a zero and not an empty reading: unread and unimportant are different facts.
    expect(unread.reading).toBeNull();
    expect(unread.attempts).toBe(2);
  });
});

describe("the watch list", () => {
  it("sends the defaulted fields the contract lists as required, and reads the answer's flag", async () => {
    let seen: unknown;
    server.use(
      http.post(`${BASE}/channels`, async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json({
          channel: {
            channel_id: "UC1",
            title: "Sim Złoto PL",
            handle: "@simzloto",
            language: "",
            profile: "market",
            alert_rule: "always",
            active: true,
            added_by: "operator",
            added_at: "2026-09-27T09:00:00Z",
            last_discovery_at: null,
          },
          created: false,
        });
      }),
    );

    const result = await createYoutubeApi(BASE).followChannel("@simzloto", "always", signal());

    expect(seen).toEqual({ reference: "@simzloto", alert_rule: "always", language: "", profile: "market" });
    expect(result.created).toBe(false);
    expect(result.channel.lastDiscoveryAt).toBeNull();
  });

  it("takes a channel off with a 204 and reads nothing from it", async () => {
    server.use(http.delete(`${BASE}/channels/UC1`, () => new HttpResponse(null, { status: 204 })));

    await expect(createYoutubeApi(BASE).unfollowChannel("UC1", signal())).resolves.toBeUndefined();
  });

  it("carries the module's reason when it refuses", async () => {
    server.use(
      http.post(`${BASE}/channels`, () =>
        HttpResponse.json({ detail: { detail: "the watch list holds 100 channels" } }, { status: 422 }),
      ),
    );

    await expect(createYoutubeApi(BASE).followChannel("@x", "never", signal())).rejects.toMatchObject({
      kind: "refused",
    });
  });
});

describe("a workbench without the package", () => {
  it("answers 404 to the state route, which the view reads as absence and not as an empty archive", async () => {
    server.use(http.get(`${BASE}/state`, () => HttpResponse.json({ detail: "Not Found" }, { status: 404 })));

    const failure = await createYoutubeApi(BASE)
      .state(signal())
      .catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(MarketDataError);
    expect((failure as MarketDataError).kind).toBe("not-found");
  });
});
