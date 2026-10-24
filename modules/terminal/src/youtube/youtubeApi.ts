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

export type FilmState = Schemas["VideoOut"]["state"];

/** A model's reading of a film, without its text — a fact about what a model said, never shown without naming the prompt. */
export interface Reading {
  promptId: number;
  promptName: string;
  /** Which version of the prompt made it; the prompt's words may have changed since. */
  promptVersion: number;
  summary: string;
  impactScore: number;
  model: string;
  analysedAt: Date;
  simulated: boolean;
}

/** The same with the text, laid out in Markdown as its prompt asked. Only a single film carries it. */
export interface FullReading extends Reading {
  text: string;
}

export interface FilmDetail {
  film: Film;
  /** The film's own prompt's reading first. */
  readings: FullReading[];
}

export interface Prompt {
  id: number;
  name: string;
  /** The one that is always there: it can be edited and never deleted. */
  seeded: boolean;
  version: number;
  body: string;
  createdAt: Date;
  updatedAt: Date;
  /** The channels whose new films it reads. */
  channels: string[];
}

export interface PromptsPage {
  prompts: Prompt[];
  maxChars: number;
  ceiling: number;
}

/** What the loop and a topic added without limits of its own run by; ranges are the ones a save is checked against. */
export interface LoopSettings {
  pollIntervalMinutes: number;
  topicIntervalMinutes: number;
  topicMaxVideos: number;
  /** False while nobody has saved: the values are the workbench's own configuration. */
  saved: boolean;
  pollIntervalRange: readonly [number, number];
  topicIntervalRange: readonly [number, number];
  topicMaxVideosRange: readonly [number, number];
}

export type LoopSettingsPatch = Partial<Pick<LoopSettings, "pollIntervalMinutes" | "topicIntervalMinutes" | "topicMaxVideos">>;

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
  /** The prompt this film is read by. */
  promptId: number;
  /** By the film's own prompt; `null` until a model has read it — never a zero: unread and unimportant are different facts. */
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
  active: boolean;
  addedBy: "operator" | "agent";
  promptId: number;
  lastDiscoveryAt: Date | null;
  /** Which of the channel's new films to process, in the operator's words; null processes all of them. */
  filter: string | null;
}

export type RunOutcome = Schemas["TopicRunOut"]["outcome"];
export type UnscreenedReason = NonNullable<Schemas["TopicRunOut"]["unscreened_reason"]>;

/** One attempt to search a topic, and its report. The counts are of what the source returned. */
export interface TopicRun {
  id: number;
  topicId: number;
  /** What was searched, as it stood then — the topic may since have gone. */
  phrase: string;
  ranAt: Date;
  outcome: RunOutcome;
  results: number;
  known: number;
  outOfBounds: number;
  proposed: number;
  rejected: number;
  unscreened: number;
  unscreenedReason: UnscreenedReason | null;
  /** Why a run failed or was skipped. */
  error: string | null;
}

export interface Topic {
  id: number;
  phrase: string;
  language: string;
  intervalMinutes: number;
  maxVideosPerRun: number;
  active: boolean;
  addedBy: "operator" | "agent";
  lastRunAt: Date | null;
  /** How the latest search ended; null before the first one. */
  lastRun: TopicRun | null;
}

export type CandidateVerdict = Schemas["CandidateOut"]["verdict"];
export type CandidateDecision = NonNullable<Schemas["CandidateOut"]["decision"]>;
export type CandidateView = Schemas["CandidatesOut"]["view"];
export type CandidateSort = Schemas["CandidatesOut"]["sort"];

/** A film a topic's search found, offered and not read: nothing is transcribed for it until the operator says so. */
export interface Candidate {
  videoId: string;
  /** The film on YouTube. */
  url: string;
  title: string;
  channelId: string | null;
  channelTitle: string;
  /** The phrase that found it. */
  topic: string;
  publishedAt: Date;
  durationSeconds: number | null;
  foundAt: Date;
  /** `unscreened` where no model could look at it — offered all the same. */
  verdict: CandidateVerdict;
  /** One sentence from the model on why the film may be worth watching, or why not. */
  reason: string | null;
  /** What the operator did with it; `null` is not decided yet. */
  decision: CandidateDecision | null;
  simulated: boolean;
}

export interface IgnoredChannel {
  channelId: string;
  title: string;
  ignoredAt: Date;
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
  /** Active channels with a filter: their new films wait to be judged while there is no model or the day is spent. */
  channelsFiltered: number;
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

function mapReading(raw: Schemas["ReadingSummary"]): Reading {
  return {
    promptId: raw.prompt_id,
    promptName: raw.prompt_name,
    promptVersion: raw.prompt_version,
    summary: raw.summary_pl,
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
    promptId: raw.prompt_id,
    reading: raw.reading ? mapReading(raw.reading) : null,
  };
}

function mapPrompt(raw: Schemas["PromptOut"]): Prompt {
  return {
    id: raw.id,
    name: raw.name,
    seeded: raw.seeded,
    version: raw.version,
    body: raw.body,
    createdAt: new Date(raw.created_at),
    updatedAt: new Date(raw.updated_at),
    channels: raw.channels,
  };
}

function mapSettings(raw: Schemas["SettingsOut"]): LoopSettings {
  return {
    pollIntervalMinutes: raw.poll_interval_minutes,
    topicIntervalMinutes: raw.topic_interval_minutes,
    topicMaxVideos: raw.topic_max_videos,
    saved: raw.saved,
    pollIntervalRange: raw.poll_interval_range,
    topicIntervalRange: raw.topic_interval_range,
    topicMaxVideosRange: raw.topic_max_videos_range,
  };
}

function mapChannel(raw: Schemas["ChannelOut"]): Channel {
  return {
    channelId: raw.channel_id,
    title: raw.title,
    handle: raw.handle ?? null,
    active: raw.active,
    addedBy: raw.added_by,
    promptId: raw.prompt_id,
    lastDiscoveryAt: optionalDate(raw.last_discovery_at),
    filter: raw.filter ?? null,
  };
}

function mapRun(raw: Schemas["TopicRunOut"]): TopicRun {
  return {
    id: raw.id,
    topicId: raw.topic_id,
    phrase: raw.phrase,
    ranAt: new Date(raw.ran_at),
    outcome: raw.outcome,
    results: raw.results,
    known: raw.known,
    outOfBounds: raw.out_of_bounds,
    proposed: raw.proposed,
    rejected: raw.rejected,
    unscreened: raw.unscreened,
    unscreenedReason: raw.unscreened_reason ?? null,
    error: raw.error ?? null,
  };
}

function mapTopic(raw: Schemas["TopicOut"]): Topic {
  return {
    id: raw.id,
    phrase: raw.phrase,
    language: raw.language,
    intervalMinutes: raw.interval_minutes,
    maxVideosPerRun: raw.max_videos_per_run,
    active: raw.active,
    addedBy: raw.added_by,
    lastRunAt: optionalDate(raw.last_run_at),
    lastRun: raw.last_run ? mapRun(raw.last_run) : null,
  };
}

function mapCandidate(raw: Schemas["CandidateOut"]): Candidate {
  return {
    videoId: raw.video_id,
    url: raw.url,
    title: raw.title,
    channelId: raw.channel_id ?? null,
    channelTitle: raw.channel_title,
    topic: raw.topic,
    publishedAt: new Date(raw.published_at),
    durationSeconds: raw.duration_seconds ?? null,
    foundAt: new Date(raw.found_at),
    verdict: raw.verdict,
    reason: raw.reason ?? null,
    decision: raw.decision ?? null,
    simulated: raw.simulated,
  };
}

function mapState(raw: Schemas["StateOut"]): ArchiveState {
  return {
    simulating: raw.simulating,
    modelConfigured: raw.model_configured,
    channelsFiltered: raw.channels_filtered,
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
  /** `state` narrows the list; `filtered_out` is the only way to see the films a channel's filter turned away. */
  recentFilms(hours: number, signal: AbortSignal, state?: FilmState): Promise<FilmsPage>;
  state(signal: AbortSignal): Promise<ArchiveState>;
  transcript(videoId: string, offset: number, signal: AbortSignal): Promise<TranscriptPage>;
  channels(signal: AbortSignal): Promise<{ channels: Channel[]; ceiling: number }>;
  followChannel(
    reference: string,
    promptId: number | null,
    filter: string | null,
    signal: AbortSignal,
  ): Promise<FollowResult>;
  setChannel(
    channelId: string,
    /** `filter: null` takes the filter off; leaving it out keeps it. */
    patch: { active?: boolean; promptId?: number; filter?: string | null },
    signal: AbortSignal,
  ): Promise<Channel>;
  unfollowChannel(channelId: string, signal: AbortSignal): Promise<void>;
  topics(signal: AbortSignal): Promise<{ topics: Topic[]; ceiling: number }>;
  /** Searches of the topics, newest first — all of them, or one topic's. */
  topicRuns(query: { topicId?: number }, signal: AbortSignal): Promise<{ runs: TopicRun[]; retentionDays: number }>;
  addTopic(request: TopicRequest, signal: AbortSignal): Promise<TopicResult>;
  setTopic(id: number, patch: { active?: boolean }, signal: AbortSignal): Promise<Topic>;
  removeTopic(id: number, signal: AbortSignal): Promise<void>;
  candidates(query: { view: CandidateView; sort: CandidateSort }, signal: AbortSignal): Promise<Candidate[]>;
  /** Follows the candidate's channel; the channel's other open candidates are settled with it. */
  followCandidateChannel(videoId: string, promptId: number | null, signal: AbortSignal): Promise<FollowResult>;
  /** Names the candidate's film for analysis, as if its address had been pasted. */
  analyseCandidate(
    videoId: string,
    promptId: number | null,
    signal: AbortSignal,
  ): Promise<{ videoId: string; title: string; created: boolean }>;
  dismissCandidate(videoId: string, signal: AbortSignal): Promise<void>;
  ignoreCandidateChannel(videoId: string, signal: AbortSignal): Promise<void>;
  ignoredChannels(signal: AbortSignal): Promise<IgnoredChannel[]>;
  unignoreChannel(channelId: string, signal: AbortSignal): Promise<void>;
  analyse(
    reference: string,
    promptId: number | null,
    signal: AbortSignal,
  ): Promise<{ videoId: string; title: string; created: boolean }>;
  film(videoId: string, signal: AbortSignal): Promise<FilmDetail>;
  /** Reads a film already transcribed once more, by another prompt, in the background. */
  readAgain(videoId: string, promptId: number, signal: AbortSignal): Promise<void>;
  prompts(signal: AbortSignal): Promise<PromptsPage>;
  createPrompt(request: { name: string; body: string }, signal: AbortSignal): Promise<Prompt>;
  updatePrompt(id: number, patch: { name?: string; body?: string }, signal: AbortSignal): Promise<Prompt>;
  deletePrompt(id: number, signal: AbortSignal): Promise<void>;
  settings(signal: AbortSignal): Promise<LoopSettings>;
  updateSettings(patch: LoopSettingsPatch, signal: AbortSignal): Promise<LoopSettings>;
}

/** Characters of transcript per page: enough to read, small enough that a page is a request and not a download. */
export const TRANSCRIPT_PAGE = 4000;

export function createYoutubeApi(httpBase: string, identity: Identity = noIdentity): YoutubeApi {
  const http = jsonClient("youtube-data", mapStatus, identity);

  return {
    async recentFilms(hours, signal, state) {
      const narrowed = state === undefined ? "" : `&state=${state}`;
      const raw = await http.json<Schemas["VideosOut"]>(`${httpBase}/videos?hours=${hours}&limit=100${narrowed}`, {
        signal,
      });
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

    async followChannel(reference, promptId, filter, signal) {
      // The contract lists the defaulted fields as required in a request body, so they are said.
      const body: Schemas["ChannelIn"] = { reference, language: "", prompt_id: promptId, filter };
      const raw = await http.json<Schemas["ChannelAddedOut"]>(`${httpBase}/channels`, {
        signal,
        method: "POST",
        body,
      });
      return { channel: mapChannel(raw.channel), created: raw.created };
    },

    async setChannel(channelId, patch, signal) {
      const body: Schemas["ChannelPatch"] = {
        ...(patch.active === undefined ? {} : { active: patch.active }),
        ...(patch.promptId === undefined ? {} : { prompt_id: patch.promptId }),
        ...(patch.filter === undefined ? {} : { filter: patch.filter }),
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

    async topicRuns(query, signal) {
      const narrowed = query.topicId === undefined ? "" : `&topic_id=${query.topicId}`;
      const raw = await http.json<Schemas["TopicRunsOut"]>(`${httpBase}/topic-runs?limit=100${narrowed}`, { signal });
      return { runs: raw.runs.map(mapRun), retentionDays: raw.retention_days };
    },

    async addTopic(request, signal) {
      const body: Schemas["TopicIn"] = {
        phrase: request.phrase,
        language: request.language ?? "",
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
      const body: Schemas["TopicPatch"] = patch.active === undefined ? {} : { active: patch.active };
      return mapTopic(
        await http.json<Schemas["TopicOut"]>(`${httpBase}/topics/${id}`, { signal, method: "PATCH", body }),
      );
    },

    async removeTopic(id, signal) {
      await http.send(`${httpBase}/topics/${id}`, { signal, method: "DELETE" });
    },

    async candidates({ view, sort }, signal) {
      const raw = await http.json<Schemas["CandidatesOut"]>(`${httpBase}/candidates?view=${view}&sort=${sort}&limit=100`, {
        signal,
      });
      return raw.candidates.map(mapCandidate);
    },

    async followCandidateChannel(videoId, promptId, signal) {
      const body: Schemas["CandidateChoice"] = { prompt_id: promptId };
      const raw = await http.json<Schemas["CandidateChannelOut"]>(
        `${httpBase}/candidates/${encodeURIComponent(videoId)}/follow-channel`,
        { signal, method: "POST", body },
      );
      return { channel: mapChannel(raw.channel), created: raw.created };
    },

    async analyseCandidate(videoId, promptId, signal) {
      const body: Schemas["CandidateChoice"] = { prompt_id: promptId };
      const raw = await http.json<Schemas["QueuedOut"]>(
        `${httpBase}/candidates/${encodeURIComponent(videoId)}/analyse`,
        { signal, method: "POST", body },
      );
      return { videoId: raw.video_id, title: raw.title, created: raw.created };
    },

    async dismissCandidate(videoId, signal) {
      await http.send(`${httpBase}/candidates/${encodeURIComponent(videoId)}/dismiss`, { signal, method: "POST" });
    },

    async ignoreCandidateChannel(videoId, signal) {
      await http.send(`${httpBase}/candidates/${encodeURIComponent(videoId)}/ignore-channel`, {
        signal,
        method: "POST",
      });
    },

    async ignoredChannels(signal) {
      const raw = await http.json<Schemas["IgnoredChannelsOut"]>(`${httpBase}/ignored-channels`, { signal });
      return raw.channels.map((channel) => ({
        channelId: channel.channel_id,
        title: channel.channel_title,
        ignoredAt: new Date(channel.ignored_at),
      }));
    },

    async unignoreChannel(channelId, signal) {
      await http.send(`${httpBase}/ignored-channels/${encodeURIComponent(channelId)}`, { signal, method: "DELETE" });
    },

    async analyse(reference, promptId, signal) {
      const body: Schemas["AnalyseIn"] = { reference, prompt_id: promptId };
      const raw = await http.json<Schemas["QueuedOut"]>(`${httpBase}/videos`, { signal, method: "POST", body });
      return { videoId: raw.video_id, title: raw.title, created: raw.created };
    },

    async film(videoId, signal) {
      const raw = await http.json<Schemas["VideoDetailOut"]>(`${httpBase}/videos/${encodeURIComponent(videoId)}`, {
        signal,
      });
      return {
        film: mapFilm(raw),
        readings: raw.readings.map((reading) => ({ ...mapReading(reading), text: reading.text })),
      };
    },

    async readAgain(videoId, promptId, signal) {
      const body: Schemas["ReadIn"] = { prompt_id: promptId };
      await http.send(`${httpBase}/videos/${encodeURIComponent(videoId)}/readings`, { signal, method: "POST", body });
    },

    async prompts(signal) {
      const raw = await http.json<Schemas["PromptsOut"]>(`${httpBase}/prompts`, { signal });
      return { prompts: raw.prompts.map(mapPrompt), maxChars: raw.max_chars, ceiling: raw.ceiling };
    },

    async createPrompt(request, signal) {
      const body: Schemas["PromptIn"] = { name: request.name, body: request.body };
      return mapPrompt(await http.json<Schemas["PromptOut"]>(`${httpBase}/prompts`, { signal, method: "POST", body }));
    },

    async updatePrompt(id, patch, signal) {
      const body: Schemas["PromptPatch"] = {
        ...(patch.name === undefined ? {} : { name: patch.name }),
        ...(patch.body === undefined ? {} : { body: patch.body }),
      };
      return mapPrompt(
        await http.json<Schemas["PromptOut"]>(`${httpBase}/prompts/${id}`, { signal, method: "PATCH", body }),
      );
    },

    async deletePrompt(id, signal) {
      await http.send(`${httpBase}/prompts/${id}`, { signal, method: "DELETE" });
    },

    async settings(signal) {
      return mapSettings(await http.json<Schemas["SettingsOut"]>(`${httpBase}/settings`, { signal }));
    },

    async updateSettings(patch, signal) {
      const body: Schemas["SettingsPatch"] = {
        ...(patch.pollIntervalMinutes === undefined ? {} : { poll_interval_minutes: patch.pollIntervalMinutes }),
        ...(patch.topicIntervalMinutes === undefined ? {} : { topic_interval_minutes: patch.topicIntervalMinutes }),
        ...(patch.topicMaxVideos === undefined ? {} : { topic_max_videos: patch.topicMaxVideos }),
      };
      return mapSettings(
        await http.json<Schemas["SettingsOut"]>(`${httpBase}/settings`, { signal, method: "PATCH", body }),
      );
    },
  };
}
