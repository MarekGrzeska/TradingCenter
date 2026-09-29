/**
 * The news archive's wire shape turned into the one this app renders. A delay is a range or a stated
 * reason — never a zero standing in for "not measured".
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.social.generated";
import { postsBase } from "../data/config";
import { jsonClient } from "../data/http";

type Schemas = components["schemas"];

export type DelayUnmeasured = NonNullable<Schemas["NewsItemOut"]["delay_unmeasured"]>;
export type SourceStatus = Schemas["NewsSourceOut"]["status"];

export interface NewsItem {
  source: string;
  externalId: string;
  publisher: string;
  title: string;
  summary: string;
  content: string;
  url: string | null;
  publishedAt: Date | null;
  firstSeenAt: Date;
  delayMinSeconds: number | null;
  delayMaxSeconds: number | null;
  delayUnmeasured: DelayUnmeasured | null;
  keptAt: Date | null;
  expiresAt: Date | null;
}

export interface NewsList {
  items: NewsItem[];
  count: number;
  truncated: boolean;
}

export interface NewsSource {
  source: string;
  publisher: string;
  status: SourceStatus;
  lastSuccessAt: Date | null;
  lastFailure: string | null;
  items24h: number;
  unmeasured24h: number;
  delayMinMedianSeconds: number | null;
  delayMinP90Seconds: number | null;
  delayMaxMedianSeconds: number | null;
  delayMaxP90Seconds: number | null;
  newestPublishedAt: Date | null;
}

export interface NewsQuery {
  minutes?: number;
  sources?: string[];
  q?: string;
  kept?: boolean;
  limit?: number;
}

export interface NewsApi {
  getNews(query: NewsQuery, signal: AbortSignal): Promise<NewsList>;
  getNewsSources(signal: AbortSignal): Promise<NewsSource[]>;
  setKept(source: string, externalId: string, keep: boolean, signal?: AbortSignal): Promise<NewsItem>;
}

const date = (value: string | null | undefined): Date | null => (value ? new Date(value) : null);

export function mapItem(raw: Schemas["NewsItemOut"]): NewsItem {
  return {
    source: raw.source,
    externalId: raw.external_id,
    publisher: raw.publisher,
    title: raw.title,
    summary: raw.summary,
    content: raw.content,
    url: raw.url ?? null,
    publishedAt: date(raw.published_at),
    firstSeenAt: new Date(raw.first_seen_at),
    delayMinSeconds: raw.delay_min_seconds ?? null,
    delayMaxSeconds: raw.delay_max_seconds ?? null,
    delayUnmeasured: raw.delay_unmeasured ?? null,
    keptAt: date(raw.kept_at),
    expiresAt: date(raw.expires_at),
  };
}

export function mapSource(raw: Schemas["NewsSourceOut"]): NewsSource {
  return {
    source: raw.source,
    publisher: raw.publisher,
    status: raw.status,
    lastSuccessAt: date(raw.last_success_at),
    lastFailure: raw.last_failure ?? null,
    items24h: raw.items_24h,
    unmeasured24h: raw.unmeasured_24h,
    delayMinMedianSeconds: raw.delay_min_median_seconds ?? null,
    delayMinP90Seconds: raw.delay_min_p90_seconds ?? null,
    delayMaxMedianSeconds: raw.delay_max_median_seconds ?? null,
    delayMaxP90Seconds: raw.delay_max_p90_seconds ?? null,
    newestPublishedAt: date(raw.newest_published_at),
  };
}

export function createNewsApi(
  base: string = postsBase(),
  identity: Identity = noIdentity,
): NewsApi {
  const http = jsonClient("social-data", { 404: "not-found", 422: "refused" }, identity);

  return {
    async getNews(query, signal) {
      const params = new URLSearchParams();
      if (query.minutes !== undefined) params.set("minutes", String(query.minutes));
      for (const source of query.sources ?? []) params.append("source", source);
      if (query.q) params.set("q", query.q);
      if (query.kept) params.set("kept", "true");
      if (query.limit !== undefined) params.set("limit", String(query.limit));
      const raw = await http.json<Schemas["NewsOut"]>(`${base}/news?${params}`, { signal });
      return { items: raw.items.map(mapItem), count: raw.count, truncated: raw.truncated };
    },

    async getNewsSources(signal) {
      const raw = await http.json<Schemas["NewsSourcesOut"]>(`${base}/news/sources`, { signal });
      return raw.sources.map(mapSource);
    },

    async setKept(source, externalId, keep, signal = new AbortController().signal) {
      const body: Schemas["KeepIn"] = { source, external_id: externalId, keep };
      return mapItem(
        await http.json<Schemas["NewsItemOut"]>(`${base}/news/keep`, { method: "PUT", body, signal }),
      );
    },
  };
}
