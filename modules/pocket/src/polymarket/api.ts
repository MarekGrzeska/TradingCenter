/**
 * The archive's wire shape turned into the one this app renders. A probability is a number on 0..1 here
 * and everywhere below it; the single multiplication by a hundred lives in `probability.ts`.
 */

import type { components } from "../data/contract.polymarket.generated";
import { archiveBase } from "../data/config";
import { jsonClient } from "../data/http";

type Schemas = components["schemas"];

export interface Outcome {
  id: number;
  name: string;
  /** The market's probability for this outcome, or `null` when nothing has been collected yet. */
  price: number | null;
  /** When that price was observed. A price without one is a number nobody can date, so the two
   *  travel together and the row shows both. */
  priceAt: Date | null;
}

export interface Market {
  id: number;
  question: string;
  /** What this market is called inside its event — a candidate's name where the question is the
   *  same for all of them. */
  label: string | null;
  /** One of a mutually-exclusive set. The prices across that set need not sum to 1 and MUST NOT be
   *  presented as if they did, which is why nothing here ever adds them up. */
  negRisk: boolean;
  resolvedOutcome: string | null;
  outcomes: Outcome[];
}

export type CollectionState = Schemas["CollectionOut"]["state"];

export interface TrackedEvent {
  id: number;
  providerEventId: string;
  slug: string;
  title: string;
  /** The event on polymarket.com, for the operator to open. */
  url: string;
  group: string | null;
  collection: { state: CollectionState; lastSampleAt: Date | null; reason: string | null };
  markets: Market[];
}

export type WindowName = Schemas["WindowChange"]["window"];

/** One window's movement, or the named reason there is none: a window the collected history does not
 *  reach is a reason, never a zero — a zero would be a claim about the market. */
export interface WindowChange {
  window: WindowName;
  change: number | null;
  unavailable: string | null;
}

export interface OutcomeChanges {
  outcomeId: number;
  name: string;
  windows: WindowChange[];
}

export interface Group {
  id: number;
  name: string;
  eventCount: number;
}

export interface TrackResult {
  event: TrackedEvent;
  /** True when the event was already observed. Not an error, and no second observation was created. */
  alreadyTracked: boolean;
}

/** A moment, or `null`. In one place because `new Date(null!)` is the epoch rather than an error — a
 *  wrong answer that renders. */
function moment(raw: string | null | undefined): Date | null {
  return raw === null || raw === undefined ? null : new Date(raw);
}

function mapEvent(raw: Schemas["TrackedEventOut"]): TrackedEvent {
  return {
    id: raw.id,
    providerEventId: raw.provider_event_id,
    slug: raw.slug,
    title: raw.title,
    url: raw.url,
    group: raw.group,
    collection: {
      state: raw.collection.state,
      lastSampleAt: moment(raw.collection.last_sample_at),
      reason: raw.collection.reason,
    },
    markets: raw.markets.map((market) => ({
      id: market.id,
      question: market.question,
      label: market.label,
      negRisk: market.neg_risk,
      resolvedOutcome: market.resolved_outcome,
      // The provider's own ordering is what pairs an outcome with its token, so it is kept as it
      // arrives rather than sorted into something that reads better.
      outcomes: market.outcomes.map((outcome) => ({
        id: outcome.id,
        name: outcome.name,
        price: outcome.price,
        priceAt: moment(outcome.price_at),
      })),
    })),
  };
}

/**
 * 403 is a refusal of the caller, not a sign-in problem: the gate authorizes an application. 409 is the
 * tracking ceiling, 502 the provider rather than the archive — the one status here worth retrying.
 */
const STATUS_KINDS = {
  403: "refused",
  404: "not-found",
  409: "refused",
  422: "refused",
  502: "upstream",
} as const;

export interface PolymarketApi {
  listEvents(signal: AbortSignal): Promise<TrackedEvent[]>;
  listGroups(signal: AbortSignal): Promise<Group[]>;
  /** One event's windows, asked for when a card is opened rather than for every event on every poll:
   *  each window is a query per outcome, and a phone shows one card at a time. */
  changes(providerEventId: string, signal: AbortSignal): Promise<OutcomeChanges[]>;
  trackEvent(reference: string, signal: AbortSignal, group?: string): Promise<TrackResult>;
  /** The observation and everything collected for it, in one act — **the only way an event leaves the
   *  list**. The archive also offers a history-only delete; this client does not, so nobody finds it. */
  removeEvent(providerEventId: string, signal: AbortSignal): Promise<void>;
}

export function createPolymarketApi(base: string = archiveBase()): PolymarketApi {
  const http = jsonClient("polymarket-data", STATUS_KINDS);

  return {
    async listEvents(signal) {
      const raw = await http.json<Schemas["TrackedEventOut"][]>(`${base}/events`, { signal });
      return raw.map(mapEvent);
    },

    async listGroups(signal) {
      const raw = await http.json<Schemas["GroupOut"][]>(`${base}/groups`, { signal });
      return raw.map((group) => ({ id: group.id, name: group.name, eventCount: group.event_count }));
    },

    async changes(providerEventId, signal) {
      const raw = await http.json<Schemas["ChangesOut"]>(
        `${base}/events/${encodeURIComponent(providerEventId)}/changes`,
        { signal },
      );
      return raw.outcomes.map((outcome) => ({
        outcomeId: outcome.outcome_id,
        name: outcome.name,
        windows: outcome.windows.map((window) => ({
          window: window.window,
          change: window.change,
          unavailable: window.unavailable,
        })),
      }));
    },

    async trackEvent(reference, signal, group) {
      const body: Schemas["TrackRequest"] = { reference, ...(group ? { group } : {}) };
      const raw = await http.json<Schemas["TrackResult"]>(`${base}/events`, {
        signal,
        method: "POST",
        body,
      });
      return { event: mapEvent(raw.event), alreadyTracked: raw.already_tracked };
    },

    async removeEvent(providerEventId, signal) {
      // `send` rather than `json`: the archive answers 204, and `Response.json()` on an empty body
      // throws a SyntaxError that would surface as a broken screen rather than as the success it is.
      await http.send(`${base}/events/${encodeURIComponent(providerEventId)}`, {
        signal,
        method: "DELETE",
      });
    },
  };
}
