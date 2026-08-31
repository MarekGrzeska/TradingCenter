/**
 * Its own client rather than a route under another module's: a different App Service behind a different gate, so
 * it carries a token for **its** audience. Wire shapes stay in the generated contract; this maps them to dates.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.social.generated";
import { jsonClient, statusMapper } from "../data/http";

type Schemas = components["schemas"];

export interface Post {
  source: string;
  externalId: string;
  author: string;
  content: string;
  url: string | null;
  isRepost: boolean;
  publishedAt: Date;
  /** The Polish reading, or `null` where no model has produced one. The card shows the
   *  original in that case rather than an empty body. */
  translatedContent: string | null;
  topics: string[];
  /** What a model made of this post's market impact, 1..10, or `null` when none has read it.
   *  Never rendered as a zero: unread and unimportant are different facts. */
  impactScore: number | null;
  /** Which model produced the score. A reading is a fact about what a model said, so the
   *  screen can name it. */
  analysedModel: string | null;
  analysedAt: Date | null;
}

export interface SourceState {
  source: string;
  collectingSince: Date;
  lastSuccessAt: Date | null;
  lastFailureReason: string | null;
  /** The archive has not heard from this source for several intervals. The screen says so
   *  instead of showing an empty list that reads as a quiet day. */
  stale: boolean;
}

export interface ArchiveState {
  sources: SourceState[];
  postsInWindow: number;
  windowHours: number;
  /** False means no model is configured, so scores and translations stay empty by
   *  configuration — which the screen has to say rather than leave the operator guessing. */
  modelConfigured: boolean;
}

export interface PostsPage {
  posts: Post[];
  windowFrom: Date;
  windowTo: Date;
}

function date(raw: string): Date {
  return new Date(raw);
}

function optionalDate(raw: string | null | undefined): Date | null {
  return raw ? new Date(raw) : null;
}

function mapPost(raw: Schemas["PostOut"]): Post {
  return {
    source: raw.source,
    externalId: raw.external_id,
    author: raw.author,
    content: raw.content,
    url: raw.url ?? null,
    isRepost: raw.is_repost,
    publishedAt: date(raw.published_at),
    translatedContent: raw.translated_content ?? null,
    topics: raw.topics ?? [],
    impactScore: raw.impact_score ?? null,
    analysedModel: raw.analysed_model ?? null,
    analysedAt: optionalDate(raw.analysed_at),
  };
}

function mapState(raw: Schemas["StateOut"]): ArchiveState {
  return {
    sources: raw.sources.map((source) => ({
      source: source.source,
      collectingSince: date(source.collecting_since),
      lastSuccessAt: optionalDate(source.last_success_at),
      lastFailureReason: source.last_failure_reason ?? null,
      stale: source.stale,
    })),
    postsInWindow: raw.posts_in_window,
    windowHours: raw.window_hours,
    modelConfigured: raw.model_configured,
  };
}

const mapStatus = statusMapper({ 404: "not-found", 422: "refused" });

export interface SocialApi {
  recentPosts(hours: number, signal: AbortSignal): Promise<PostsPage>;
  state(signal: AbortSignal): Promise<ArchiveState>;
}

export function createSocialApi(httpBase: string, identity: Identity = noIdentity): SocialApi {
  const http = jsonClient("social-data", mapStatus, identity);

  return {
    async recentPosts(hours, signal) {
      const raw = await http.json<Schemas["PostsOut"]>(
        `${httpBase}/posts?hours=${hours}&limit=200`,
        { signal },
      );
      return {
        posts: raw.posts.map(mapPost),
        windowFrom: date(raw.window_from),
        windowTo: date(raw.window_to),
      };
    },

    async state(signal) {
      return mapState(await http.json<Schemas["StateOut"]>(`${httpBase}/state`, { signal }));
    },
  };
}
