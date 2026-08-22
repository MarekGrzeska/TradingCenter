/**
 * The prediction-market archive, read straight from `polymarket-data`.
 *
 * Its own client rather than a route under the archive's: a different App Service behind
 * a different gate, so it carries a token minted for **its** audience and nobody else's
 * (specs/terminal-identity). The wire types come from `contract.polymarket.generated.ts`,
 * which is generated from that module's own Pydantic models — this file maps them to what
 * the views want and is the only place the two shapes meet.
 *
 * **A probability is a number on 0..1, never a percentage**, at every layer including
 * this one. The module says so in every field description it publishes and the mistake it
 * guards against is silent: reading 0,62 as 62 is wrong by two orders of magnitude and
 * throws nothing on the way. Nothing here multiplies by a hundred; formatting for a human
 * is the view's business and it does it once.
 *
 * **Nothing here computes a change.** The seven windows come from the module, which
 * measures them against the base point it actually holds — the provider's spacing wobbles,
 * so the base point is rarely the window's edge, and two readings subtracted here would be
 * a different number with no way to say so.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.polymarket.generated";
import { jsonClient, statusMapper } from "../data/http";

type Schemas = components["schemas"];

// --- what the views work in -----------------------------------------------------------

export interface Outcome {
  id: number;
  name: string;
  /** The market's probability for this outcome on 0..1, or `null` when nothing has been
   *  collected yet. Not a percentage. */
  price: number | null;
  /** When that price was observed. A price without one is a number nobody can date, so
   *  the two travel together and the view shows both. */
  priceAt: Date | null;
  lastTrade: number | null;
  /** How far back this outcome's collected history reaches — the boundary the chart
   *  draws rather than implies. */
  collectedFrom: Date | null;
}

export interface Market {
  id: number;
  question: string;
  /** What this market is called inside its event — a candidate's name where the question
   *  is the same for all of them. */
  label: string | null;
  /** One of a mutually-exclusive set. The Yes prices across that set need not sum to 1
   *  and MUST NOT be presented as if they did. */
  negRisk: boolean;
  resolvedOutcome: string | null;
  outcomes: Outcome[];
}

export type CollectionState = Schemas["CollectionOut"]["state"];

export interface Collection {
  state: CollectionState;
  lastSampleAt: Date | null;
  /** Why collection is not running, when it is not. */
  reason: string | null;
}

export interface TrackedEvent {
  id: number;
  providerEventId: string;
  slug: string;
  title: string;
  /** The event on polymarket.com, for the operator to open. */
  url: string;
  group: string | null;
  trackedAt: Date | null;
  collection: Collection;
  markets: Market[];
}

/** The seven the module computes. Taken from the generated contract rather than retyped,
 *  so a window added there is a compile error here and not a silently missing column. */
export type WindowName = Schemas["WindowChange"]["window"];

/** One window's movement, or the named reason there is none.
 *
 *  `change` and `unavailable` are exclusive and exhaustive on purpose: a window the
 *  collected history does not reach is a reason, never a zero. A zero would be a claim
 *  about the market where the truth is a claim about the archive. */
export interface WindowChange {
  window: WindowName;
  change: number | null;
  unavailable: string | null;
  /** The moment the base point actually came from — rarely the window's edge. */
  baselineAt: Date | null;
}

export interface OutcomeChanges {
  outcomeId: number;
  name: string;
  price: number | null;
  windows: WindowChange[];
}

export interface EventChanges {
  eventId: number;
  outcomes: OutcomeChanges[];
}

/** One row of the whole-screen read. Flat rather than nested: the snapshot exists to be
 *  joined onto a list the view already has. */
export interface SnapshotEntry {
  eventId: number;
  eventSlug: string;
  marketId: number;
  marketLabel: string | null;
  outcomeId: number;
  outcomeName: string;
  price: number | null;
  priceAt: Date | null;
}

export interface PricePoint {
  at: Date;
  price: number | null;
  lastTrade: number | null;
}

export interface History {
  outcomeId: number;
  points: PricePoint[];
  /** The earliest moment actually collected for. The absence before it is not a market
   *  that was silent — it is history the provider will not give back. */
  collectedFrom: Date | null;
  collectedTo: Date | null;
}

export interface Group {
  id: number;
  name: string;
  eventCount: number;
}

export interface TrackResult {
  event: TrackedEvent;
  /** True when the event was already observed. Not an error, and no second observation
   *  was created — the view says so rather than pretending it did something. */
  alreadyTracked: boolean;
}

export interface DeletionResult {
  samplesDeleted: number;
  rangesDeleted: number;
}

// --- wire → domain --------------------------------------------------------------------

/** A moment, or `null`. Kept in one place because every shape here has at least one, and
 *  `new Date(null!)` is the epoch rather than an error — a wrong answer that renders. */
function moment(raw: string | null | undefined): Date | null {
  return raw === null || raw === undefined ? null : new Date(raw);
}

function mapOutcome(raw: Schemas["OutcomeOut"]): Outcome {
  return {
    id: raw.id,
    name: raw.name,
    price: raw.price,
    priceAt: moment(raw.price_at),
    lastTrade: raw.last_trade,
    collectedFrom: moment(raw.collected_from),
  };
}

function mapMarket(raw: Schemas["MarketOut"]): Market {
  return {
    id: raw.id,
    question: raw.question,
    label: raw.label,
    negRisk: raw.neg_risk,
    resolvedOutcome: raw.resolved_outcome,
    // The provider's own ordering is what pairs an outcome with its token, so it is kept
    // as it arrives rather than sorted into something that reads better.
    outcomes: raw.outcomes.map(mapOutcome),
  };
}

function mapEvent(raw: Schemas["TrackedEventOut"]): TrackedEvent {
  return {
    id: raw.id,
    providerEventId: raw.provider_event_id,
    slug: raw.slug,
    title: raw.title,
    url: raw.url,
    group: raw.group,
    trackedAt: moment(raw.tracked_at),
    collection: {
      state: raw.collection.state,
      lastSampleAt: moment(raw.collection.last_sample_at),
      reason: raw.collection.reason,
    },
    markets: raw.markets.map(mapMarket),
  };
}

function mapWindow(raw: Schemas["WindowChange"]): WindowChange {
  return {
    window: raw.window,
    change: raw.change,
    unavailable: raw.unavailable,
    baselineAt: moment(raw.baseline_at),
  };
}

function mapChanges(raw: Schemas["ChangesOut"]): EventChanges {
  return {
    eventId: raw.event_id,
    outcomes: raw.outcomes.map((outcome) => ({
      outcomeId: outcome.outcome_id,
      name: outcome.name,
      price: outcome.price,
      windows: outcome.windows.map(mapWindow),
    })),
  };
}

function mapSnapshotEntry(raw: Schemas["SnapshotEntry"]): SnapshotEntry {
  return {
    eventId: raw.event_id,
    eventSlug: raw.event_slug,
    marketId: raw.market_id,
    marketLabel: raw.market_label,
    outcomeId: raw.outcome_id,
    outcomeName: raw.outcome_name,
    price: raw.price,
    priceAt: moment(raw.price_at),
  };
}

function mapHistory(raw: Schemas["HistoryOut"]): History {
  return {
    outcomeId: raw.outcome_id,
    points: raw.points.map((point) => ({
      at: new Date(point.at),
      price: point.price,
      lastTrade: point.last_trade,
    })),
    collectedFrom: moment(raw.collected_from),
    collectedTo: moment(raw.collected_to),
  };
}

function mapGroup(raw: Schemas["GroupOut"]): Group {
  return { id: raw.id, name: raw.name, eventCount: raw.event_count };
}

// --- the client -----------------------------------------------------------------------

/**
 * What each refusal means here.
 *
 * 403 is `refused` rather than a sign-in problem, and that is the distinction this module
 * makes and the platform cannot: a caller Easy Auth admitted may still have no business
 * on the REST contract, because the gate authorizes an application and not a route
 * (`polymarket_data/caller_access.py`). 401 is not in this table and cannot be —
 * `jsonClient` turns it into a lost session before a mapper is reached.
 *
 * 409 is the tracking ceiling: understood, declined, and unchanged on a retry. 502 is the
 * provider, not this module — the one status here worth retrying.
 */
const mapStatus = statusMapper({
  403: "refused",
  404: "not-found",
  409: "refused",
  422: "refused",
  502: "upstream",
});

export interface PolymarketApi {
  listEvents(signal: AbortSignal, options?: { groupId?: number; includeEnded?: boolean }): Promise<TrackedEvent[]>;
  readEvent(providerEventId: string, signal: AbortSignal): Promise<TrackedEvent>;
  /** Every tracked outcome's last price, in one request. Never one per outcome: prices
   *  fetched separately come from different moments, and a market whose outcomes were
   *  priced at different instants shows a total that never existed. */
  snapshot(signal: AbortSignal): Promise<SnapshotEntry[]>;
  changes(providerEventId: string, signal: AbortSignal): Promise<EventChanges>;
  history(
    outcomeId: number,
    signal: AbortSignal,
    range?: { since?: Date; until?: Date },
  ): Promise<History>;
  trackEvent(reference: string, signal: AbortSignal, group?: string): Promise<TrackResult>;
  /** Stops the sampling and returns the event as it now stands. **No sample is
   *  deleted** — that is `deleteHistory`, and keeping them apart is the whole reason a
   *  button called "stop" may not read as a button called "delete". */
  endTracking(providerEventId: string, signal: AbortSignal): Promise<TrackedEvent>;
  deleteHistory(providerEventId: string, signal: AbortSignal): Promise<DeletionResult>;
  listGroups(signal: AbortSignal): Promise<Group[]>;
  createGroup(name: string, signal: AbortSignal): Promise<Group>;
  deleteGroup(groupId: number, signal: AbortSignal): Promise<void>;
  /** `null` takes the event out of every group without ending its observation. */
  assignGroup(eventId: number, groupId: number | null, signal: AbortSignal): Promise<void>;
}

export function createPolymarketApi(
  httpBase: string,
  identity: Identity = noIdentity,
): PolymarketApi {
  const http = jsonClient("polymarket-data", mapStatus, identity);

  return {
    async listEvents(signal, options) {
      const query = new URLSearchParams();
      if (options?.groupId !== undefined) query.set("group_id", String(options.groupId));
      if (options?.includeEnded) query.set("include_ended", "true");
      const suffix = query.size === 0 ? "" : `?${query}`;
      const raw = await http.json<Schemas["TrackedEventOut"][]>(`${httpBase}/events${suffix}`, {
        signal,
      });
      return raw.map(mapEvent);
    },

    async readEvent(providerEventId, signal) {
      const raw = await http.json<Schemas["TrackedEventOut"]>(
        `${httpBase}/events/${encodeURIComponent(providerEventId)}`,
        { signal },
      );
      return mapEvent(raw);
    },

    async snapshot(signal) {
      const raw = await http.json<Schemas["SnapshotOut"]>(`${httpBase}/snapshot`, { signal });
      return raw.entries.map(mapSnapshotEntry);
    },

    async changes(providerEventId, signal) {
      const raw = await http.json<Schemas["ChangesOut"]>(
        `${httpBase}/events/${encodeURIComponent(providerEventId)}/changes`,
        { signal },
      );
      return mapChanges(raw);
    },

    async history(outcomeId, signal, range) {
      const query = new URLSearchParams();
      if (range?.since) query.set("since", range.since.toISOString());
      if (range?.until) query.set("until", range.until.toISOString());
      const suffix = query.size === 0 ? "" : `?${query}`;
      const raw = await http.json<Schemas["HistoryOut"]>(
        `${httpBase}/outcomes/${outcomeId}/history${suffix}`,
        { signal },
      );
      return mapHistory(raw);
    },

    async trackEvent(reference, signal, group) {
      const body: Schemas["TrackRequest"] = { reference, ...(group ? { group } : {}) };
      const raw = await http.json<Schemas["TrackResult"]>(`${httpBase}/events`, {
        signal,
        method: "POST",
        body,
      });
      return { event: mapEvent(raw.event), alreadyTracked: raw.already_tracked };
    },

    async endTracking(providerEventId, signal) {
      const raw = await http.json<Schemas["TrackedEventOut"]>(
        `${httpBase}/events/${encodeURIComponent(providerEventId)}/tracking`,
        { signal, method: "DELETE" },
      );
      return mapEvent(raw);
    },

    async deleteHistory(providerEventId, signal) {
      const raw = await http.json<Schemas["DeletionResult"]>(
        `${httpBase}/events/${encodeURIComponent(providerEventId)}/history`,
        { signal, method: "DELETE" },
      );
      return { samplesDeleted: raw.samples_deleted, rangesDeleted: raw.ranges_deleted };
    },

    async listGroups(signal) {
      const raw = await http.json<Schemas["GroupOut"][]>(`${httpBase}/groups`, { signal });
      return raw.map(mapGroup);
    },

    async createGroup(name, signal) {
      const body: Schemas["GroupRequest"] = { name };
      const raw = await http.json<Schemas["GroupOut"]>(`${httpBase}/groups`, {
        signal,
        method: "POST",
        body,
      });
      return mapGroup(raw);
    },

    // `send`, not `json`: both answer 204 with no body at all, and `Response.json()` on
    // an empty body throws a SyntaxError that would surface as a broken screen rather
    // than as the success it is.
    async deleteGroup(groupId, signal) {
      await http.send(`${httpBase}/groups/${groupId}`, { signal, method: "DELETE" });
    },

    async assignGroup(eventId, groupId, signal) {
      const body: Schemas["AssignRequest"] = { group_id: groupId };
      await http.send(`${httpBase}/events/${eventId}/group`, {
        signal,
        method: "PUT",
        body,
      });
    },
  };
}
