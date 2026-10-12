/**
 * Its own client rather than a route under another module's: a different package behind a different record, so it carries a
 * token for **its** audience. Wire shapes stay in the generated contract; this maps them to dates and to the names the screen
 * uses. The one thing to remember about the back end: it may not be there at all — a workbench without the YouTube database
 * answers 404 to every route here, and the view says so rather than showing an empty archive.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.youtube.generated";
import { jsonClient, statusMapper } from "../data/http";

type Schemas = components["schemas"];

export type AlertRule = Schemas["ChannelIn"]["alert_rule"];
export type FilmState = Schemas["VideoOut"]["state"];
export type Sentiment = Schemas["InstrumentOut"]["sentiment"];

export interface Instrument {
  name: string;
  epic: string | null;
  sentiment: Sentiment;
  /** How sure the *speaker* sounds, 1..5 — not how sure the model is. */
  conviction: number;
  horizon: Schemas["InstrumentOut"]["horizon"];
}

export interface Prediction {
  instrument: string;
  claim: string;
  level: number | null;
  by: string | null;
}

/** A model's reading of a film — a fact about what a model said, never shown without naming it. */
export interface Reading {
  summary: string;
  keyPoints: string[];
  instruments: Instrument[];
  predictions: Prediction[];
  topics: string[];
  impactScore: number;
  model: string;
  analysedAt: Date;
  simulated: boolean;
}

export interface Film {
  videoId: string;
  url: string;
  title: string;
  channelId: string | null;
  channelTitle: string;
  publishedAt: Date;
  durationSeconds: number | null;
  liveStatus: Schemas["VideoOut"]["live_status"];
  state: FilmState;
  skipReason: string | null;
  attempts: number;
  nextAttemptAt: Date | null;
  /** Comes from the simulation: the film does not exist. */
  simulated: boolean;
  /** `null` until a model has read it — never a zero: unread and unimportant are different facts. */
  reading: Reading | null;
}

export interface FilmsPage {
  films: Film[];
  windowFrom: Date;
  windowTo: Date;
}

export interface TranscriptPage {
  text: string;
  language: string;
  provider: string;
  automatic: boolean;
  /** The model that listened to the film; null for captions. */
  model: string | null;
  simulated: boolean;
  offset: number;
  totalChars: number;
  nextOffset: number | null;
}

export interface Channel {
  channelId: string;
  title: string;
  handle: string | null;
  alertRule: AlertRule;
  active: boolean;
  addedBy: "operator" | "agent";
  lastDiscoveryAt: Date | null;
}

export interface Topic {
  id: number;
  phrase: string;
  language: string;
  intervalMinutes: number;
  maxVideosPerRun: number;
  alertRule: AlertRule;
  active: boolean;
  addedBy: "operator" | "agent";
  lastRunAt: Date | null;
}

export interface ProviderState {
  role: Schemas["ProviderOut"]["role"];
  name: string;
  unit: string;
  spentToday: number;
  ceiling: number;
  /** The day's ceiling is reached, so the provider is not asked until midnight UTC. */
  exhausted: boolean;
  /** Refused us the last time we asked and has not answered since — a fact about us, not about any film. */
  blocked: boolean;
  blockedReason: string | null;
}

export interface ArchiveState {
  /** Some provider is the simulation: films may not exist. Said on the screen for as long as it is true. */
  simulating: boolean;
  /** False means no reading is being made, by configuration. */
  modelConfigured: boolean;
  /** False means nobody is told, by configuration. */
  alertsConfigured: boolean;
  providers: ProviderState[];
  /** Films still on their road, by state — exact. */
  waiting: Record<string, number>;
  /** The loop has not completed a pass for several intervals. */
  stale: boolean;
  loopAgeSeconds: number | null;
}

export interface FollowResult {
  channel: Channel;
  created: boolean;
}

export interface TopicRequest {
  phrase: string;
  language?: string;
  intervalMinutes?: number;
  maxVideosPerRun?: number;
  alertRule: AlertRule;
}

export interface TopicResult {
  topic: Topic;
  created: boolean;
  /** Which of its limits came from the settings rather than from the request. */
  defaultsApplied: string[];
}

function optionalDate(raw: string | null | undefined): Date | null {
  return raw ? new Date(raw) : null;
}

function mapReading(raw: Schemas["ReadingOut"]): Reading {
  return {
    summary: raw.summary_pl,
    keyPoints: raw.key_points,
    instruments: raw.instruments.map((view) => ({
      name: view.name,
      epic: view.epic ?? null,
      sentiment: view.sentiment,
      conviction: view.conviction,
      horizon: view.horizon,
    })),
    predictions: raw.predictions.map((p) => ({
      instrument: p.instrument,
      claim: p.claim,
      level: p.level ?? null,
      by: p.by ?? null,
    })),
    topics: raw.topics,
    impactScore: raw.impact_score,
    model: raw.model,
    analysedAt: new Date(raw.analysed_at),
    simulated: raw.simulated,
  };
}

function mapFilm(raw: Schemas["VideoOut"]): Film {
  return {
    videoId: raw.video_id,
    url: raw.url,
    title: raw.title,
    channelId: raw.channel_id ?? null,
    channelTitle: raw.channel_title,
    publishedAt: new Date(raw.published_at),
    durationSeconds: raw.duration_seconds ?? null,
    liveStatus: raw.live_status,
    state: raw.state,
    skipReason: raw.skip_reason ?? null,
    attempts: raw.attempts,
    nextAttemptAt: optionalDate(raw.next_attempt_at),
    simulated: raw.simulated,
    reading: raw.reading ? mapReading(raw.reading) : null,
  };
}

function mapChannel(raw: Schemas["ChannelOut"]): Channel {
  return {
    channelId: raw.channel_id,
    title: raw.title,
    handle: raw.handle ?? null,
    alertRule: raw.alert_rule,
    active: raw.active,
    addedBy: raw.added_by,
    lastDiscoveryAt: optionalDate(raw.last_discovery_at),
  };
}

function mapTopic(raw: Schemas["TopicOut"]): Topic {
  return {
    id: raw.id,
    phrase: raw.phrase,
    language: raw.language,
    intervalMinutes: raw.interval_minutes,
    maxVideosPerRun: raw.max_videos_per_run,
    alertRule: raw.alert_rule,
    active: raw.active,
    addedBy: raw.added_by,
    lastRunAt: optionalDate(raw.last_run_at),
  };
}

function mapState(raw: Schemas["StateOut"]): ArchiveState {
  return {
    simulating: raw.simulating,
    modelConfigured: raw.model_configured,
    alertsConfigured: raw.alerts_configured,
    providers: raw.providers.map((provider) => ({
      role: provider.role,
      name: provider.name,
      unit: provider.unit,
      spentToday: provider.spent_today,
      ceiling: provider.ceiling,
      exhausted: provider.exhausted,
      blocked: provider.blocked,
      blockedReason: provider.blocked_reason ?? null,
    })),
    waiting: raw.waiting,
    stale: raw.stale,
    loopAgeSeconds: raw.loop?.age_seconds ?? null,
  };
}

// 404 is "no such thing" on a route with an id in it, and "this workbench has no YouTube archive" on the rest — the view
// tells the two apart by which call it was making.
const mapStatus = statusMapper({ 404: "not-found", 422: "refused" });

export interface YoutubeApi {
  recentFilms(hours: number, signal: AbortSignal): Promise<FilmsPage>;
  state(signal: AbortSignal): Promise<ArchiveState>;
  transcript(videoId: string, offset: number, signal: AbortSignal): Promise<TranscriptPage>;
  channels(signal: AbortSignal): Promise<{ channels: Channel[]; ceiling: number }>;
  followChannel(reference: string, alertRule: AlertRule, signal: AbortSignal): Promise<FollowResult>;
  setChannel(
    channelId: string,
    patch: { alertRule?: AlertRule; active?: boolean },
    signal: AbortSignal,
  ): Promise<Channel>;
  unfollowChannel(channelId: string, signal: AbortSignal): Promise<void>;
  topics(signal: AbortSignal): Promise<{ topics: Topic[]; ceiling: number }>;
  addTopic(request: TopicRequest, signal: AbortSignal): Promise<TopicResult>;
  setTopic(
    id: number,
    patch: { alertRule?: AlertRule; active?: boolean },
    signal: AbortSignal,
  ): Promise<Topic>;
  removeTopic(id: number, signal: AbortSignal): Promise<void>;
  analyse(reference: string, signal: AbortSignal): Promise<{ videoId: string; title: string; created: boolean }>;
}

/** Characters of transcript per page: enough to read, small enough that a page is a request and not a download. */
export const TRANSCRIPT_PAGE = 4000;

export function createYoutubeApi(httpBase: string, identity: Identity = noIdentity): YoutubeApi {
  const http = jsonClient("youtube-data", mapStatus, identity);

  return {
    async recentFilms(hours, signal) {
      const raw = await http.json<Schemas["VideosOut"]>(`${httpBase}/videos?hours=${hours}&limit=100`, { signal });
      return {
        films: raw.videos.map(mapFilm),
        windowFrom: new Date(raw.window_from),
        windowTo: new Date(raw.window_to),
      };
    },

    async state(signal) {
      return mapState(await http.json<Schemas["StateOut"]>(`${httpBase}/state`, { signal }));
    },

    async transcript(videoId, offset, signal) {
      const raw = await http.json<Schemas["TranscriptPageOut"]>(
        `${httpBase}/videos/${encodeURIComponent(videoId)}/transcript?offset=${offset}&limit=${TRANSCRIPT_PAGE}`,
        { signal },
      );
      return {
        text: raw.text,
        language: raw.language,
        provider: raw.provider,
        automatic: raw.automatic,
        model: raw.model ?? null,
        simulated: raw.simulated,
        offset: raw.offset,
        totalChars: raw.total_chars,
        nextOffset: raw.next_offset ?? null,
      };
    },

    async channels(signal) {
      const raw = await http.json<Schemas["ChannelsOut"]>(`${httpBase}/channels`, { signal });
      return { channels: raw.channels.map(mapChannel), ceiling: raw.ceiling };
    },

    async followChannel(reference, alertRule, signal) {
      // The contract lists the defaulted fields as required in a request body, so they are said.
      const body: Schemas["ChannelIn"] = { reference, alert_rule: alertRule, language: "", profile: "market" };
      const raw = await http.json<Schemas["ChannelAddedOut"]>(`${httpBase}/channels`, {
        signal,
        method: "POST",
        body,
      });
      return { channel: mapChannel(raw.channel), created: raw.created };
    },

    async setChannel(channelId, patch, signal) {
      const body: Schemas["ChannelPatch"] = {
        ...(patch.alertRule === undefined ? {} : { alert_rule: patch.alertRule }),
        ...(patch.active === undefined ? {} : { active: patch.active }),
      };
      return mapChannel(
        await http.json<Schemas["ChannelOut"]>(`${httpBase}/channels/${encodeURIComponent(channelId)}`, {
          signal,
          method: "PATCH",
          body,
        }),
      );
    },

    async unfollowChannel(channelId, signal) {
      // `send` rather than `json`: the module answers 204 — what it could return about a thing that is no longer on the list
      // is a shape somebody would be tempted to read.
      await http.send(`${httpBase}/channels/${encodeURIComponent(channelId)}`, { signal, method: "DELETE" });
    },

    async topics(signal) {
      const raw = await http.json<Schemas["TopicsOut"]>(`${httpBase}/topics`, { signal });
      return { topics: raw.topics.map(mapTopic), ceiling: raw.ceiling };
    },

    async addTopic(request, signal) {
      const body: Schemas["TopicIn"] = {
        phrase: request.phrase,
        alert_rule: request.alertRule,
        language: request.language ?? "",
        profile: "market",
        ...(request.intervalMinutes === undefined ? {} : { interval_minutes: request.intervalMinutes }),
        ...(request.maxVideosPerRun === undefined ? {} : { max_videos_per_run: request.maxVideosPerRun }),
      };
      const raw = await http.json<Schemas["TopicAddedOut"]>(`${httpBase}/topics`, {
        signal,
        method: "POST",
        body,
      });
      return { topic: mapTopic(raw.topic), created: raw.created, defaultsApplied: raw.defaults_applied };
    },

    async setTopic(id, patch, signal) {
      const body: Schemas["TopicPatch"] = {
        ...(patch.alertRule === undefined ? {} : { alert_rule: patch.alertRule }),
        ...(patch.active === undefined ? {} : { active: patch.active }),
      };
      return mapTopic(
        await http.json<Schemas["TopicOut"]>(`${httpBase}/topics/${id}`, { signal, method: "PATCH", body }),
      );
    },

    async removeTopic(id, signal) {
      await http.send(`${httpBase}/topics/${id}`, { signal, method: "DELETE" });
    },

    async analyse(reference, signal) {
      const body: Schemas["AnalyseIn"] = { reference };
      const raw = await http.json<Schemas["QueuedOut"]>(`${httpBase}/videos`, { signal, method: "POST", body });
      return { videoId: raw.video_id, title: raw.title, created: raw.created };
    },
  };
}
