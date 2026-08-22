import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { polymarketIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { EventCard } from "./EventCard";
import { GroupBar } from "./GroupBar";
import { TrackEventDialog } from "./TrackEventDialog";
import {
  createPolymarketApi,
  type Group,
  type PolymarketApi,
  type SnapshotEntry,
  type TrackedEvent,
} from "./polymarketApi";

/**
 * The prediction markets the operator is watching.
 *
 * Until this tab existed the only way to see any of it was to ask the model, which
 * inverts how the rest of this terminal works: the operator looks, and the model is a
 * second pair of eyes rather than the only one. A probability moves slowly and means
 * something only in a window, and a number in a sentence shows no movement at all.
 *
 * **Two reads, not one per row.** The structure — events, their markets and outcomes —
 * comes from `/events`; every current price comes from `/snapshot` in a single request.
 * That is a correctness rule and not a saving: prices fetched per outcome come from
 * different moments, and a market whose outcomes were priced at different instants shows
 * a total that never existed (specs/terminal-polymarket, "Ceny całej listy biorą się
 * z jednego żądania"). The windows are per event and arrive only for an event the
 * operator opens — seven windows for fifty events would be fifty requests nobody asked
 * for.
 */

/** How often the prices are re-asked. The module samples every 60s, so anything faster
 *  is asking for the same answer; anything much slower and the age beside a price starts
 *  doing the work of a refresh button. */
const POLL_MS = 30_000;

const NO_EVENTS: TrackedEvent[] = [];
const NO_ENTRIES: SnapshotEntry[] = [];
const NO_GROUPS: Group[] = [];

export function PolymarketView({ api }: { api?: PolymarketApi } = {}) {
  const client = useMemo(
    () => api ?? createPolymarketApi(resolveEndpoints().polymarketHttp, polymarketIdentity),
    [api],
  );

  const [group, setGroup] = useState<number | null>(null);
  const [tracking, setTracking] = useState(false);

  const events = useRead<TrackedEvent[]>({
    key: ["polymarket", "events", group],
    read: (signal) =>
      client.listEvents(signal, group === null ? undefined : { groupId: group }),
    initial: NO_EVENTS,
    fallbackMessage: "could not read the tracked events",
  });

  const snapshot = useRead<SnapshotEntry[]>({
    key: ["polymarket", "snapshot"],
    read: (signal) => client.snapshot(signal),
    initial: NO_ENTRIES,
    fallbackMessage: "could not read the current prices",
    pollMs: POLL_MS,
  });

  const groups = useRead<Group[]>({
    key: ["polymarket", "groups"],
    read: (signal) => client.listGroups(signal),
    initial: NO_GROUPS,
    fallbackMessage: "could not read the groups",
  });

  // Outcome id -> its latest price, so a card looks its rows up rather than scanning the
  // whole snapshot once per outcome.
  const prices = useMemo(() => {
    const byOutcome = new Map<number, SnapshotEntry>();
    for (const entry of snapshot.value) byOutcome.set(entry.outcomeId, entry);
    return byOutcome;
  }, [snapshot.value]);

  const empty = events.status === "ready" && events.value.length === 0;

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Polymarket</h1>
        <span className="text-xs text-ink-faint">
          probabilities on a 0–1 scale, shown as percent · prices refreshed every{" "}
          {POLL_MS / 1000}s
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button size="xs" onClick={() => setTracking(true)}>
            Track event
          </Button>
          <Button
            size="xs"
            tone="muted"
            onClick={() => {
              events.reload();
              snapshot.reload();
            }}
          >
            Refresh now
          </Button>
        </div>
      </header>

      <GroupBar
        client={client}
        groups={groups.value}
        selected={group}
        onSelect={setGroup}
        onChanged={() => {
          groups.reload();
          events.reload();
        }}
      />

      {/* Two failures, told apart, because the operator's next move differs. A refusal is
          a permission that has not been granted — this module decides who reaches its REST
          contract, and the platform's gate cannot (specs/terminal-polymarket, "Zakładka
          odróżnia odmowę od niedostępności modułu"). */}
      {events.error !== null && (
        <UnreachableNotice onRetry={events.reload}>{events.error}</UnreachableNotice>
      )}
      {events.error === null && snapshot.error !== null && (
        <UnreachableNotice onRetry={snapshot.reload}>
          The prices could not be refreshed — {snapshot.error}. What is shown is the last
          answer, not the state now.
        </UnreachableNotice>
      )}

      {events.status === "loading" && (
        <p className="text-xs text-ink-faint">Reading the tracked events…</p>
      )}

      {empty && (
        <p className="text-xs text-ink-muted">
          Nothing is being tracked. Bring an event under observation — from here, or by
          asking the agent — and its probabilities start being collected every minute.
        </p>
      )}

      {/* `flex-1` is what makes this the scrolling region rather than a block that stops at
          its content: without it the list never grows, so the tab ended in dead space below
          the last event and the last row was clipped instead of scrolled to. The pair
          `min-h-0 flex-1 overflow-auto` is what `InstrumentsView` and `CollectionHistoryView`
          already use for the same job. */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {events.value.map((event) => (
          <EventCard
            key={event.id}
            event={event}
            prices={prices}
            client={client}
            groups={groups.value}
            onChanged={() => {
              events.reload();
              groups.reload();
            }}
          />
        ))}
      </div>

      {tracking && (
        <TrackEventDialog
          client={client}
          groups={groups.value}
          onClose={() => setTracking(false)}
          onTracked={() => {
            events.reload();
            groups.reload();
            snapshot.reload();
          }}
        />
      )}
    </section>
  );
}
