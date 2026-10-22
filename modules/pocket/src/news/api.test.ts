import { describe, expect, it, vi } from "vitest";
import type { components } from "../data/contract.social.generated";
import { createNewsApi, mapItem, mapSource } from "./api";

type Item = components["schemas"]["NewsItemOut"];
type Source = components["schemas"]["NewsSourceOut"];

const item: Item = {
  source: "reuters",
  external_id: "https://x/1",
  publisher: "Reuters",
  title: "Oil jumps",
  summary: "",
  content: "",
  url: null,
  published_at: "2026-09-29T10:00:00Z",
  first_seen_at: "2026-09-29T10:05:00Z",
  previous_fetch_at: "2026-09-29T10:03:00Z",
  delay_min_seconds: 180,
  delay_max_seconds: 300,
  delay_unmeasured: null,
  kept_at: null,
  expires_at: "2026-10-06T10:05:00Z",
};

describe("news mappers", () => {
  it("turns snake_case and ISO strings into the domain shape", () => {
    const mapped = mapItem(item);
    expect(mapped.externalId).toBe("https://x/1");
    expect(mapped.publishedAt).toEqual(new Date("2026-09-29T10:00:00Z"));
    expect(mapped.delayMinSeconds).toBe(180);
    expect(mapped.keptAt).toBeNull();
    expect(mapped.expiresAt).toEqual(new Date("2026-10-06T10:05:00Z"));
  });

  it("keeps a missing delay as null with its reason, never a zero", () => {
    const mapped = mapItem({
      ...item,
      published_at: null,
      delay_min_seconds: null,
      delay_max_seconds: null,
      delay_unmeasured: "no_publish_time",
    });
    expect(mapped.publishedAt).toBeNull();
    expect(mapped.delayMinSeconds).toBeNull();
    expect(mapped.delayUnmeasured).toBe("no_publish_time");
  });

  it("maps the body and sends the window as minutes", async () => {
    expect(mapItem({ ...item, content: "One.\n\nTwo." }).content).toBe("One.\n\nTwo.");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [], count: 0, truncated: false })));
    vi.stubGlobal("fetch", fetchMock);
    await createNewsApi("http://x").getNews({ minutes: 15, limit: 300 }, new AbortController().signal);
    vi.unstubAllGlobals();
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe("http://x/news?minutes=15&limit=300");
  });

  it("maps a source's day", () => {
    const raw: Source = {
      source: "reuters",
      publisher: "Reuters",
      url: "https://x",
      interval_seconds: 60,
      status: "failing",
      last_attempt_at: null,
      last_success_at: "2026-09-29T09:00:00Z",
      last_failure: "http 403",
      last_failure_at: null,
      newest_published_at: null,
      items_24h: 12,
      unmeasured_24h: 2,
      delay_min_median_seconds: 60,
      delay_min_p90_seconds: 120,
      delay_max_median_seconds: 180,
      delay_max_p90_seconds: 400,
    };
    const mapped = mapSource(raw);
    expect(mapped.status).toBe("failing");
    expect(mapped.lastFailure).toBe("http 403");
    expect(mapped.delayMaxP90Seconds).toBe(400);
    expect(mapped.newestPublishedAt).toBeNull();
  });
});
