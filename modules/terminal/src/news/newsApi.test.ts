import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createNewsApi } from "./newsApi";

/** The wire↔domain seam: past it everything is `Date`s and camelCase, and nothing knows the module's JSON. */

const HTTP_BASE = "http://social.test";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const signal = () => new AbortController().signal;

const ITEM = {
  source: "aljazeera",
  external_id: "https://www.aljazeera.com/news/2026/9/29/talks",
  publisher: "Al Jazeera",
  title: "US-Iran talks",
  summary: "",
  url: "https://www.aljazeera.com/news/2026/9/29/talks",
  published_at: "2026-09-29T15:09:00Z",
  first_seen_at: "2026-09-29T15:14:00Z",
  previous_fetch_at: "2026-09-29T15:12:00Z",
  delay_min_seconds: 180,
  delay_max_seconds: 300,
  delay_unmeasured: null,
  kept_at: null,
  expires_at: "2026-10-27T15:14:00Z",
};

describe("news", () => {
  it("asks with the window, the sources and the text, and maps what comes back", async () => {
    let asked = new URL("http://none");
    server.use(
      http.get(`${HTTP_BASE}/news`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json({
          items: [ITEM, { ...ITEM, external_id: "b", published_at: null, delay_min_seconds: null, delay_max_seconds: null, delay_unmeasured: "no_publish_time" }],
          count: 2,
          truncated: true,
          window_from: "2026-09-29T09:00:00Z",
          window_to: "2026-09-29T15:00:00Z",
        });
      }),
    );

    const page = await createNewsApi(HTTP_BASE).news(
      { hours: 6, sources: ["aljazeera", "irna"], text: " iran ", kept: false },
      signal(),
    );

    expect(asked.searchParams.get("hours")).toBe("6");
    expect(asked.searchParams.getAll("source")).toEqual(["aljazeera", "irna"]);
    expect(asked.searchParams.get("q")).toBe("iran");
    expect(page.truncated).toBe(true);
    expect(page.items[0]).toMatchObject({
      delayMinSeconds: 180,
      delayMaxSeconds: 300,
      keptAt: null,
    });
    expect(page.items[0]?.publishedAt).toEqual(new Date("2026-09-29T15:09:00Z"));
    expect(page.items[1]).toMatchObject({ publishedAt: null, delayUnmeasured: "no_publish_time" });
  });

  it("asks for the kept ones without a window", async () => {
    let asked = new URL("http://none");
    server.use(
      http.get(`${HTTP_BASE}/news`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json({ items: [], count: 0, truncated: false, window_from: null, window_to: null });
      }),
    );

    await createNewsApi(HTTP_BASE).news({ hours: 6, sources: [], text: "", kept: true }, signal());

    expect(asked.searchParams.get("kept")).toBe("true");
    expect(asked.searchParams.has("hours")).toBe(false);
  });
});

describe("keep", () => {
  it("sends the pair in the body, because an identifier is usually a URL", async () => {
    let body: unknown;
    server.use(
      http.put(`${HTTP_BASE}/news/keep`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...ITEM, kept_at: "2026-09-29T16:00:00Z", expires_at: null });
      }),
    );

    const kept = await createNewsApi(HTTP_BASE).keep(ITEM.source, ITEM.external_id, true, signal());

    expect(body).toEqual({ source: ITEM.source, external_id: ITEM.external_id, keep: true });
    expect(kept.keptAt).toEqual(new Date("2026-09-29T16:00:00Z"));
    expect(kept.expiresAt).toBeNull();
  });

  it("refuses with a reason where the headline is not there", async () => {
    server.use(
      http.put(`${HTTP_BASE}/news/keep`, () =>
        HttpResponse.json({ detail: { detail: "no headline" } }, { status: 404 }),
      ),
    );

    await expect(createNewsApi(HTTP_BASE).keep("x", "y", true, signal())).rejects.toBeInstanceOf(
      MarketDataError,
    );
  });
});

describe("sources", () => {
  it("maps both bounds' figures and the status", async () => {
    server.use(
      http.get(`${HTTP_BASE}/news/sources`, () =>
        HttpResponse.json({
          sources: [
            {
              source: "aljazeera", publisher: "Al Jazeera", url: "u", interval_seconds: 120, status: "ok",
              last_attempt_at: "2026-09-29T15:14:00Z", last_success_at: "2026-09-29T15:14:00Z",
              last_failure_at: null, last_failure: null, newest_published_at: "2026-09-29T15:09:00Z",
              items_24h: 40, unmeasured_24h: 2,
              delay_min_median_seconds: 100, delay_min_p90_seconds: 200,
              delay_max_median_seconds: 160, delay_max_p90_seconds: 300,
            },
          ],
          figures_window_hours: 24, tick_seconds: 30, stale_after_intervals: 6, retention_days: 28,
        }),
      ),
    );

    const [source] = await createNewsApi(HTTP_BASE).sources(signal());

    expect(source).toMatchObject({
      status: "ok",
      items24h: 40,
      unmeasured24h: 2,
      feed: { medianSeconds: 100, p90Seconds: 200 },
      waited: { medianSeconds: 160, p90Seconds: 300 },
    });
  });
});
