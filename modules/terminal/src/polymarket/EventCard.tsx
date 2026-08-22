import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { showToast } from "../ui/toastStore";
import { DeleteHistoryDialog } from "./DeleteHistoryDialog";
import { EndTrackingDialog } from "./EndTrackingDialog";
import { OutcomeHistory } from "./OutcomeHistory";
import { ProbabilityBar } from "./ProbabilityBar";
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
  // Two states. It had three for a day: the middle one — outcomes without their windows —
  // turned out to be a click nobody wanted, since an operator who unfolds an event is
  // unfolding it to see how it moved. Folded is the state that earns its keep.
  const [open, setOpen] = useState(false);
  // Resolved markets are folded, never dropped. A dated event resolves its markets one by
  // one and each stays for good: ten of them under one event is a hundred rows saying
  // nothing about now. The history behind them is the opposite of worthless — it is the
  // part the provider will not give back.
  const [showResolved, setShowResolved] = useState(false);
  const [ending, setEnding] = useState(false);
  const [deletingHistory, setDeletingHistory] = useState(false);

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
              // Handled rather than awaited into nothing: a rejected assignment used to be
              // an unhandled rejection, and the control went on showing a group the module
              // had refused to record.
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
        <Button size="2xs" tone="quiet" onClick={() => setEnding(true)}>
          Stop tracking
        </Button>
        {/* The only door to it in this system: no tool the model holds deletes a sample. */}
        <Button size="2xs" tone="critical" onClick={() => setDeletingHistory(true)}>
          Remove history
        </Button>
      </header>

      {!open && <CollapsedSummary event={event} prices={prices} />}

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

/**
 * One line, for an event nobody has opened.
 *
 * What it carries is the leading outcome of each market, up to a few — which is what an
 * operator scanning a dozen events is actually after, and is why collapsed is not the same
 * as hidden. A count alone ("3 markets") would make the fold cost a click to learn nothing.
 *
 * The leader is picked by price and the bar is drawn beside it, so the fold changes how much
 * is on screen and not what a number means.
 */
function CollapsedSummary({
  event,
  prices,
}: {
  event: TrackedEvent;
  prices: Map<number, SnapshotEntry>;
}) {
  // Live markets only. An event with one open market and nine settled ones would otherwise
  // quote 100% on something that finished in August.
  const live = event.markets.filter((market) => market.resolvedOutcome === null);
  const leaders = (live.length > 0 ? live : event.markets)
    .map((market) => {
      const priced = market.outcomes
        .map((outcome) => {
          const live = prices.get(outcome.id);
          return { outcome, price: live?.price ?? outcome.price, at: live?.priceAt ?? outcome.priceAt };
        })
        .filter((row) => row.price !== null);
      if (priced.length === 0) return null;

      // **A binary market is always quoted on Yes.** Quoting whichever outcome happens to
      // lead makes the line change its subject as the market crosses 50% — the number stays
      // large while what it is about flips, which is exactly how a fold ends up saying
      // "100%" about `No` and reading as though it were about `Yes`.
      const yes = priced.find((row) => row.outcome.name.toLowerCase() === "yes");
      const chosen =
        yes ?? [...priced].sort((a, b) => (b.price ?? 0) - (a.price ?? 0))[0];
      return { market, ...chosen };
    })
    .filter((row) => row !== null)
    .slice(0, 4);

  if (leaders.length === 0) {
    return (
      <p className="px-3 py-1.5 text-xs text-ink-faint">Nothing collected for this event yet.</p>
    );
  }

  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-xs">
      {leaders.map((row) => (
        <li key={row.market.id} className="flex items-center gap-2">
          {/* The outcome is always named. The market's label alone identifies the question
              and not the answer, so a number beside it was a number about nothing. */}
          <span className="text-ink-secondary">
            {row.market.label === null
              ? row.outcome.name
              : `${row.market.label} · ${row.outcome.name}`}
          </span>
          <ProbabilityBar price={row.price} stale={isStale(row.at)} at={row.at} />
          <span className="tabular-nums text-ink">{formatProbability(row.price)}</span>
        </li>
      ))}
      {live.length > leaders.length && (
        <li className="text-ink-faint">+{live.length - leaders.length} more</li>
      )}
      {live.length === 0 && <li className="text-ink-faint">resolved</li>}
    </ul>
  );
}

/**
 * A market that is over.
 *
 * One line: what it settled on. **No windows**, and that is the requirement rather than a
 * saving — after resolution the price stands, so every window comes out `0.0 pp` or "no
 * coverage". The first reads as "the market did not move" and the second as "the archive has
 * a hole"; the truth is a third thing, that there is nothing left to measure
 * (specs/terminal-polymarket, "Rozstrzygnięty rynek pokazany świadomie").
 *
 * The prices are still shown, because they are the answer: 100% against the outcome that
 * won is what resolution looks like.
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
          // The snapshot is the current answer; the structure read carries whatever was
          // true when the list was fetched. Preferring the snapshot is what keeps a price
          // and its moment from coming out of two different reads.
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
