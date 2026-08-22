import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { DeleteHistoryDialog } from "./DeleteHistoryDialog";
import { EndTrackingDialog } from "./EndTrackingDialog";
import { OutcomeHistory } from "./OutcomeHistory";
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
 * One tracked event: its markets, their outcomes, and — once opened — how each has moved.
 *
 * **The event is the unit, and a market is not a coin.** A market with two outcomes is
 * the special case of one with several, not the shape the rest are trimmed to, so every
 * outcome gets its own row and none is dropped for not being "Yes". Where a market is
 * `negRisk` its Yes prices belong to a mutually-exclusive set and need not sum to 1 —
 * saying so is cheaper than an operator working out why they do not.
 *
 * The seven windows are fetched when the card is opened, not with the list: they are one
 * request per event, and fifty events' worth of them is fifty requests for numbers nobody
 * has looked at yet.
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
  const [open, setOpen] = useState(false);
  const [ending, setEnding] = useState(false);
  const [deletingHistory, setDeletingHistory] = useState(false);

  const changes = useRead<EventChanges>({
    key: ["polymarket", "changes", event.providerEventId],
    read: (signal) => client.changes(event.providerEventId, signal),
    initial: NO_CHANGES,
    fallbackMessage: "the windows could not be read",
    enabled: open,
  });

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
            onChange={async (e) => {
              const raw = e.target.value;
              await client.assignGroup(
                event.id,
                raw === "" ? null : Number(raw),
                new AbortController().signal,
              );
              onChanged();
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
        <Button size="2xs" tone="quiet" onClick={() => setEnding(true)}>
          Stop tracking
        </Button>
        {/* The only door to it in this system: no tool the model holds deletes a sample. */}
        <Button size="2xs" tone="critical" onClick={() => setDeletingHistory(true)}>
          Remove history
        </Button>
      </header>

      <div className="flex flex-col gap-3 px-3 py-2">
        {event.markets.map((market) => (
          <MarketRows
            key={market.id}
            market={market}
            prices={prices}
            open={open}
            windowsFor={windowsFor}
          />
        ))}
      </div>

      {open && <OutcomeHistory client={client} event={event} />}

      {open && changes.error !== null && (
        <p className="px-3 pb-2 text-xs text-ink-faint">
          The windows could not be read — {changes.error}.
        </p>
      )}

      {deletingHistory && (
        <DeleteHistoryDialog
          client={client}
          event={event}
          onClose={() => setDeletingHistory(false)}
          onDeleted={onChanged}
        />
      )}

      {ending && (
        <EndTrackingDialog
          client={client}
          event={event}
          onClose={() => setEnding(false)}
          onEnded={() => {
            setEnding(false);
            onChanged();
          }}
        />
      )}
    </article>
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
  open,
  windowsFor,
}: {
  market: Market;
  prices: Map<number, SnapshotEntry>;
  open: boolean;
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
          // The snapshot is the current answer; the structure read carries whatever was
          // true when the list was fetched. Preferring the snapshot is what keeps a price
          // and its moment from coming out of two different reads.
          const price = live?.price ?? outcome.price;
          const priceAt = live?.priceAt ?? outcome.priceAt;
          const stale = isStale(priceAt);

          return (
            <li key={outcome.id} className="flex flex-wrap items-baseline gap-x-3 text-xs">
              <span className="min-w-32 text-ink">{outcome.name}</span>
              {price === null ? (
                <span className="text-ink-faint italic">not collected yet</span>
              ) : (
                <span className={stale ? "text-ink-muted" : "text-ink"}>
                  {formatProbability(price)}
                </span>
              )}
              {/* A price without its moment is a number nobody can date, and one that has
                  aged past the tick must not read as the price now. */}
              <span className={stale ? "text-warning" : "text-ink-faint"}>
                {formatAge(priceAt) ?? "no reading"}
              </span>
              {open && <WindowChanges windows={windowsFor(outcome.id)} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
