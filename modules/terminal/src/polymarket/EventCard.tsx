import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { showToast } from "../ui/toastStore";
import { OutcomeHistory } from "./OutcomeHistory";
import { ProbabilityBar } from "./ProbabilityBar";
import { RemoveEventDialog } from "./RemoveEventDialog";
import { WindowChanges } from "./WindowChanges";
import type {
  EventChanges,
  Group,
  Market,
  PolymarketApi,
  SnapshotEntry,
  TrackedEvent,
  WindowChange,
} from "./polymarketApi";
import { formatAge, formatProbability, isStale } from "./probability";

/**
 * One tracked event. **The event is the unit and a market is not a coin**: every outcome gets a row, and a
 * folded card carries no price at all, because a summary quoting one outcome is the reduction this forbids.
 */

const NO_CHANGES: EventChanges = { eventId: 0, outcomes: [] };

export function EventCard({
  event,
  prices,
  client,
  groups,
  onChanged,
}: {
  event: TrackedEvent;
  prices: Map<number, SnapshotEntry>;
  client: PolymarketApi;
  groups: Group[];
  onChanged(): void;
}) {
  // Two states. It had three for a day: outcomes without their windows turned out to be a click nobody
  // wanted, since an operator who unfolds an event is unfolding it to see how it moved.
  const [open, setOpen] = useState(false);
  // Resolved markets are folded, never dropped: ten under one event is a hundred rows saying nothing about
  // now, while the history behind them is the part the provider will not give back.
  const [showResolved, setShowResolved] = useState(false);
  const [removing, setRemoving] = useState(false);

  const changes = useRead<EventChanges>({
    key: ["polymarket", "changes", event.providerEventId],
    read: (signal) => client.changes(event.providerEventId, signal),
    initial: NO_CHANGES,
    fallbackMessage: "the windows could not be read",
    // Still only when unfolded: one request per event, and a folded list of a dozen would
    // otherwise be a dozen requests for numbers nobody has looked at.
    enabled: open,
  });

  // A market with a resolved outcome is finished: its price stands, so every window would
  // come out zero or short of coverage, and neither is a reading.
  const live = event.markets.filter((market) => market.resolvedOutcome === null);
  const resolved = event.markets.filter((market) => market.resolvedOutcome !== null);

  const windowsFor = (outcomeId: number) =>
    changes.value.outcomes.find((outcome) => outcome.outcomeId === outcomeId)?.windows ?? [];

  return (
    <article className="rounded border border-border">
      <header className="flex flex-wrap items-baseline gap-3 border-b border-border px-3 py-2">
        <button
          type="button"
          className="flex cursor-pointer items-baseline gap-1.5 text-sm font-medium text-ink"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
        >
          <span aria-hidden className="text-ink-faint">
            {open ? "▾" : "▸"}
          </span>
          <span>{event.title}</span>
        </button>
        <CollectionBadge event={event} />
        <label className="text-xs text-ink-faint">
          <span className="sr-only">Group for {event.title}</span>
          <select
            className="rounded border border-border bg-sunken px-1 py-0.5 text-ink"
            value={groups.find((entry) => entry.name === event.group)?.id ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              // Handled rather than awaited into nothing: a rejected assignment used to be an unhandled
              // rejection, and the control went on showing a group the module had refused to record.
              void client
                .assignGroup(event.id, raw === "" ? null : Number(raw), new AbortController().signal)
                .then(onChanged)
                .catch((cause: unknown) => {
                  showToast({
                    key: `polymarket-assign-${event.id}`,
                    severity: "error",
                    title: `Could not file “${event.title}”`,
                    detail: cause instanceof Error ? cause.message : "the module refused",
                  });
                  // Back to what the module actually holds, so the select stops claiming a
                  // group that was never assigned.
                  onChanged();
                });
            }}
          >
            {/* Out of every group, without ending the observation — the module's own
                meaning for a null group id. */}
            <option value="">no group</option>
            {groups.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>

        <a
          className="ml-auto text-xs text-ink-faint underline"
          href={event.url}
          target="_blank"
          rel="noreferrer"
        >
          on polymarket.com
        </a>
        {/* The only door to it in this system: no tool the model holds removes an
            observation, and removing one is what takes its history with it. */}
        <Button size="2xs" tone="critical" onClick={() => setRemoving(true)}>
          Remove
        </Button>
      </header>

      {open && (
        <div className="flex flex-col gap-3 px-3 py-2">
          {live.map((market) => (
            <MarketRows
              key={market.id}
              market={market}
              prices={prices}
              windowsFor={windowsFor}
            />
          ))}

          {live.length === 0 && (
            <p className="text-xs text-ink-muted">
              Every market of this event has resolved. Nothing is being collected for it any
              more; what was collected is still here.
            </p>
          )}

          {resolved.length > 0 && (
            <div className="flex flex-col gap-3">
              <Button
                size="2xs"
                tone="quiet"
                className="self-start"
                onClick={() => setShowResolved((was) => !was)}
              >
                {showResolved
                  ? `Hide ${resolved.length} resolved`
                  : `${resolved.length} resolved market${resolved.length === 1 ? "" : "s"}`}
              </Button>

              {showResolved &&
                resolved.map((market) => <ResolvedMarket key={market.id} market={market} />)}
            </div>
          )}
        </div>
      )}

      {open && <OutcomeHistory client={client} event={event} />}

      {open && changes.error !== null && (
        <p className="px-3 pb-2 text-xs text-ink-faint">
          The windows could not be read — {changes.error}.
        </p>
      )}

      {removing && (
        <RemoveEventDialog
          client={client}
          event={event}
          onClose={() => setRemoving(false)}
          onRemoved={() => {
            setRemoving(false);
            onChanged();
          }}
        />
      )}
    </article>
  );
}

/**
 * A market that is over: one line, and **no windows**. After resolution every window reads `0.0 pp` or "no
 * coverage" — "did not move" and "the archive has a hole" — where the truth is that there is nothing to measure.
 */
function ResolvedMarket({ market }: { market: Market }) {
  return (
    <div className="text-xs">
      <h3 className="flex items-baseline gap-2 text-ink-faint">
        <span>{market.label ?? market.question}</span>
        <span className="text-ink-muted">· settled on {market.resolvedOutcome}</span>
      </h3>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
        {market.outcomes.map((outcome) => (
          <li key={outcome.id} className="flex items-baseline gap-2 text-ink-faint">
            <span>{outcome.name}</span>
            <span className="tabular-nums">{formatProbability(outcome.price) ?? "—"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Being on the list does not prove prices are arriving, which is the whole reason the
 *  module publishes a collection state at all. `stalled` and `ended` carry the module's
 *  own reason rather than a guess made here. */
function CollectionBadge({ event }: { event: TrackedEvent }) {
  const { state, reason } = event.collection;
  if (state === "collecting") {
    return <span className="text-xs text-ink-faint">collecting</span>;
  }
  return (
    <span
      className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
      title={reason ?? undefined}
    >
      {state}
    </span>
  );
}

function MarketRows({
  market,
  prices,
  windowsFor,
}: {
  market: Market;
  prices: Map<number, SnapshotEntry>;
  windowsFor: (outcomeId: number) => WindowChange[];
}) {
  return (
    <div>
      <h3 className="flex items-baseline gap-2 text-xs text-ink-secondary">
        {market.label ?? market.question}
        {market.negRisk && (
          <span
            className="text-ink-faint"
            title="one of a mutually-exclusive set — these prices need not sum to 100%"
          >
            · exclusive set
          </span>
        )}
        {market.resolvedOutcome !== null && (
          <span className="text-ink-faint">· resolved: {market.resolvedOutcome}</span>
        )}
      </h3>

      <ul className="mt-1 flex flex-col gap-1">
        {market.outcomes.map((outcome) => {
          const live = prices.get(outcome.id);
          // The snapshot is the current answer; the structure read carries whatever was true when the list
          // was fetched. Preferring the snapshot keeps a price and its moment from two different reads.
          const price = live?.price ?? outcome.price;
          const priceAt = live?.priceAt ?? outcome.priceAt;
          const stale = isStale(priceAt);

          return (
            <li key={outcome.id} className="flex flex-wrap items-baseline gap-x-3 text-xs">
              <span className="min-w-32 text-ink">{outcome.name}</span>
              <ProbabilityBar price={price} stale={stale} at={priceAt} />
              {price === null ? (
                <span className="text-ink-faint italic">not collected yet</span>
              ) : (
                <span className={`tabular-nums ${stale ? "text-ink-muted" : "text-ink"}`}>
                  {formatProbability(price)}
                </span>
              )}
              {/* A price without its moment is a number nobody can date, and one that has
                  aged past the tick must not read as the price now. */}
              <span className={stale ? "text-warning" : "text-ink-faint"}>
                {formatAge(priceAt) ?? "no reading"}
              </span>
              <WindowChanges windows={windowsFor(outcome.id)} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
