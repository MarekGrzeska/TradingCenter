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
  prompt_id: 1,
  prompt_name: "Rynkowy",
  prompt_version: 2,
  summary_pl: "Autor uważa, że złoto wzrośnie.",
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
  prompt_id: 1,
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
    expect(read.reading).toMatchObject({ promptId: 1, promptName: "Rynkowy", promptVersion: 2, impactScore: 6 });
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
            prompt_id: 1,
            active: true,
            added_by: "operator",
            added_at: "2026-09-27T09:00:00Z",
            last_discovery_at: null,
          },
          created: false,
        });
      }),
    );

    const result = await createYoutubeApi(BASE).followChannel("@simzloto", null, signal());

    expect(seen).toEqual({ reference: "@simzloto", language: "", prompt_id: null });
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

    await expect(createYoutubeApi(BASE).followChannel("@x", null, signal())).rejects.toMatchObject({
      kind: "refused",
      message: expect.stringContaining("the watch list holds 100 channels"),
    });
  });
});

describe("prompts", () => {
  const PROMPT = {
    id: 3,
    name: "Technical",
    seeded: false,
    version: 2,
    body: "Levels only.",
    created_at: "2026-10-22T09:00:00Z",
    updated_at: "2026-10-22T10:00:00Z",
    channels: ["Sim Złoto PL"],
    topics: [],
  };

  it("maps a prompt with who reads by it, and sends only what changed", async () => {
    let seen: unknown;
    server.use(
      http.get(`${BASE}/prompts`, () => HttpResponse.json({ prompts: [PROMPT], max_chars: 8000, ceiling: 50 })),
      http.patch(`${BASE}/prompts/3`, async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json(PROMPT);
      }),
    );
    const api = createYoutubeApi(BASE);

    const page = await api.prompts(signal());
    await api.updatePrompt(3, { body: "Levels and volume." }, signal());

    expect(page.prompts[0]).toMatchObject({ id: 3, version: 2, channels: ["Sim Złoto PL"] });
    expect(page.prompts[0].updatedAt).toEqual(new Date("2026-10-22T10:00:00Z"));
    expect(seen).toEqual({ body: "Levels and volume." });
  });

  it("maps a film's readings with their text, the film's own prompt's first", async () => {
    server.use(
      http.get(`${BASE}/videos/simfilm0001`, () =>
        HttpResponse.json({ ...FILM, readings: [{ ...READING, text: "## Tezy\n- złoto rośnie" }] }),
      ),
    );

    const detail = await createYoutubeApi(BASE).film("simfilm0001", signal());

    expect(detail.film.promptId).toBe(1);
    expect(detail.readings[0]).toMatchObject({ promptName: "Rynkowy", text: "## Tezy\n- złoto rośnie" });
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
