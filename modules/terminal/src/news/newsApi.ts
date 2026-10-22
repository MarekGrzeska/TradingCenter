/**
 * The news over the same back end as the posts, so the same identity and the same base. Wire shapes stay in the
 * generated contract; this maps them to dates and to the words a screen needs.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.social.generated";
import { jsonClient, statusMapper } from "../data/http";
import { limitFor } from "./windows";

type Schemas = components["schemas"];

/** Why a headline has no delay. Each is a different fact and none of them is zero. */
export type Unmeasured = NonNullable<Schemas["NewsItemOut"]["delay_unmeasured"]>;
export type SourceStatus = Schemas["NewsSourceOut"]["status"];

export interface NewsItem {
  source: string;
  externalId: string;
  publisher: string;
  title: string;
  summary: string;
  /** The body where the feed carries more than a lead, paragraphs kept; empty where it does not. */
  content: string;
  url: string | null;
  publishedAt: Date | null;
  firstSeenAt: Date;
  /** How late the feed itself was: its previous fetch did not have this yet. */
  delayMinSeconds: number | null;
  /** How long from publication until this archive saw it. */
  delayMaxSeconds: number | null;
  delayUnmeasured: Unmeasured | null;
  keptAt: Date | null;
  /** When retention will remove it; `null` for a kept headline. */
  expiresAt: Date | null;
}

export interface NewsPage {
  items: NewsItem[];
  truncated: boolean;
  windowFrom: Date | null;
}

export interface Figures {
  medianSeconds: number | null;
  p90Seconds: number | null;
}

export interface NewsSource {
  source: string;
  publisher: string;
  intervalSeconds: number;
  status: SourceStatus;
  lastSuccessAt: Date | null;
  lastFailure: string | null;
  newestPublishedAt: Date | null;
  items24h: number;
  unmeasured24h: number;
  /** The lower bound of the delay: how late the feed itself is. */
  feed: Figures;
  /** The upper bound: what the operator waited. */
  waited: Figures;
}

export interface NewsQuery {
  minutes: number;
  sources: string[];
  text: string;
  kept: boolean;
}

function optionalDate(raw: string | null | undefined): Date | null {
  return raw ? new Date(raw) : null;
}

function mapItem(raw: Schemas["NewsItemOut"]): NewsItem {
  return {
    source: raw.source,
    externalId: raw.external_id,
    publisher: raw.publisher,
    title: raw.title,
    summary: raw.summary,
    content: raw.content,
    url: raw.url ?? null,
    publishedAt: optionalDate(raw.published_at),
    firstSeenAt: new Date(raw.first_seen_at),
    delayMinSeconds: raw.delay_min_seconds ?? null,
    delayMaxSeconds: raw.delay_max_seconds ?? null,
    delayUnmeasured: raw.delay_unmeasured ?? null,
    keptAt: optionalDate(raw.kept_at),
    expiresAt: optionalDate(raw.expires_at),
  };
}

function mapSource(raw: Schemas["NewsSourceOut"]): NewsSource {
  return {
    source: raw.source,
    publisher: raw.publisher,
    intervalSeconds: raw.interval_seconds,
    status: raw.status,
    lastSuccessAt: optionalDate(raw.last_success_at),
    lastFailure: raw.last_failure ?? null,
    newestPublishedAt: optionalDate(raw.newest_published_at),
    items24h: raw.items_24h,
    unmeasured24h: raw.unmeasured_24h,
    feed: {
      medianSeconds: raw.delay_min_median_seconds ?? null,
      p90Seconds: raw.delay_min_p90_seconds ?? null,
    },
    waited: {
      medianSeconds: raw.delay_max_median_seconds ?? null,
      p90Seconds: raw.delay_max_p90_seconds ?? null,
    },
  };
}

const mapStatus = statusMapper({ 404: "not-found", 422: "refused" });

export interface NewsApi {
  news(query: NewsQuery, signal: AbortSignal): Promise<NewsPage>;
  sources(signal: AbortSignal): Promise<NewsSource[]>;
  /** Idempotent both ways; answers with the headline as it now stands. */
  keep(source: string, externalId: string, keep: boolean, signal: AbortSignal): Promise<NewsItem>;
}

export function createNewsApi(httpBase: string, identity: Identity = noIdentity): NewsApi {
  const http = jsonClient("social-data", mapStatus, identity);

  return {
    async news(query, signal) {
      const params = new URLSearchParams({ limit: String(limitFor(query.minutes)) });
      if (query.kept) params.set("kept", "true");
      else params.set("minutes", String(query.minutes));
      for (const source of query.sources) params.append("source", source);
      if (query.text.trim() !== "") params.set("q", query.text.trim());
      const raw = await http.json<Schemas["NewsOut"]>(`${httpBase}/news?${params}`, { signal });
      return {
        items: raw.items.map(mapItem),
        truncated: raw.truncated,
        windowFrom: optionalDate(raw.window_from),
      };
    },

    async sources(signal) {
      const raw = await http.json<Schemas["NewsSourcesOut"]>(`${httpBase}/news/sources`, {
        signal,
      });
      return raw.sources.map(mapSource);
    },

    async keep(source, externalId, keep, signal) {
      const body: Schemas["KeepIn"] = { source, external_id: externalId, keep };
      const raw = await http.json<Schemas["NewsItemOut"]>(`${httpBase}/news/keep`, {
        method: "PUT",
        body,
        signal,
      });
      return mapItem(raw);
    },
  };
}
