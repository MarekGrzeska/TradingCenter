/**
 * The post archive's wire shape turned into the one this app renders. A reading is present or it is
 * `null` — never a zero, because "no model has read this" and "a model judged it noise" are different.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.social.generated";
import { postsBase } from "../data/config";
import { jsonClient } from "../data/http";

type Schemas = components["schemas"];

export interface Post {
  source: string;
  externalId: string;
  content: string;
  /** The Polish reading, or `null` where no model has produced one. The card falls back to the
   *  original rather than showing an empty body. */
  translatedContent: string | null;
  url: string | null;
  isRepost: boolean;
  publishedAt: Date;
  topics: string[];
  /** 1..10, or `null` when no model has read this post. */
  impactScore: number | null;
  analysedModel: string | null;
}

export interface SourceState {
  source: string;
  lastSuccessAt: Date | null;
  lastFailureReason: string | null;
  /** The archive has not heard from this source for several intervals — which the screen says
   *  instead of letting an empty list stand for it. */
  stale: boolean;
}

export interface ArchiveState {
  sources: SourceState[];
  windowHours: number;
  /** False means no model is configured, so scores and translations stay empty by configuration. */
  modelConfigured: boolean;
}

export interface SocialApi {
  recentPosts(signal: AbortSignal): Promise<Post[]>;
  state(signal: AbortSignal): Promise<ArchiveState>;
}

const WINDOW_HOURS = 24;

function mapPost(raw: Schemas["PostOut"]): Post {
  return {
    source: raw.source,
    externalId: raw.external_id,
    content: raw.content,
    translatedContent: raw.translated_content ?? null,
    url: raw.url ?? null,
    isRepost: raw.is_repost,
    publishedAt: new Date(raw.published_at),
    topics: raw.topics ?? [],
    impactScore: raw.impact_score ?? null,
    analysedModel: raw.analysed_model ?? null,
  };
}

export function createSocialApi(
  base: string = postsBase(),
  identity: Identity = noIdentity,
): SocialApi {
  const http = jsonClient("social-data", { 404: "not-found", 422: "refused" }, identity);

  return {
    async recentPosts(signal) {
      const page = await http.json<Schemas["PostsOut"]>(
        `${base}/posts?hours=${WINDOW_HOURS}&limit=100`,
        { signal },
      );
      return page.posts.map(mapPost);
    },

    async state(signal) {
      const raw = await http.json<Schemas["StateOut"]>(`${base}/state`, { signal });
      return {
        sources: raw.sources.map((source) => ({
          source: source.source,
          lastSuccessAt: source.last_success_at ? new Date(source.last_success_at) : null,
          lastFailureReason: source.last_failure_reason ?? null,
          stale: source.stale,
        })),
        windowHours: raw.window_hours,
        modelConfigured: raw.model_configured,
      };
    },
  };
}
