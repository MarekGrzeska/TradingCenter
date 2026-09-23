import { useEffect, useMemo, useRef, useState } from "react";
import type { OutcomeChanges, PolymarketApi, TrackedEvent } from "./api";
import { groupKeys, labelFor, loadFilters, saveFilters, sections } from "./grouping";
import { formatAge } from "./probability";
import { useArchive } from "./useArchive";
import { EventCard } from "./EventCard";
import { TrackEventSheet } from "./TrackEventSheet";
import { RemoveEventSheet } from "./RemoveEventSheet";
import { GroupsSheet } from "./GroupsSheet";
import { MoveEventSheet } from "./MoveEventSheet";
import { Button } from "../ui/Button";
import { PULL_THRESHOLD } from "../ui/pull";
import { usePullToRefresh } from "../ui/usePullToRefresh";
import styles from "./PolymarketScreen.module.css";

type Sheet =
  | { kind: "track" }
  | { kind: "remove"; event: TrackedEvent }
  | { kind: "move"; event: TrackedEvent }
  | { kind: "groups" }
  | null;

/** `null` means the windows for that event are on their way. An absent key means nobody has opened
 *  the card, which is a different thing and reads as a different row. */
type ChangesByEvent = Record<string, Map<number, OutcomeChanges> | null>;

export function PolymarketScreen({ api }: { api: PolymarketApi }) {
  const { events, groups, status, error, lastReadAt, refreshing, now, refresh } = useArchive(api);
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() => loadFilters());
  const [expanded, setExpanded] = useState<string[]>([]);
  const [changes, setChanges] = useState<ChangesByEvent>({});
  const [sheet, setSheet] = useState<Sheet>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const scroller = useRef<HTMLDivElement>(null);
  const pull = usePullToRefresh(scroller, refresh);

  const groupNames = useMemo(() => groups.map((group) => group.name), [groups]);
  const keys = useMemo(() => groupKeys(events, groupNames), [events, groupNames]);
  const visible = useMemo(() => sections(events, enabled), [events, enabled]);

  useEffect(() => saveFilters(enabled), [enabled]);

  // The windows of every open card, re-read whenever the archive answers. Only the open ones: each
  // window is a query per outcome, and a card nobody has opened has nowhere to show them.
  const openIds = expanded.join(" ");
  useEffect(() => {
    const controller = new AbortController();
    const ids = openIds === "" ? [] : openIds.split(" ");

    for (const id of ids) {
      void (async () => {
        try {
          const outcomes = await api.changes(id, controller.signal);
          setChanges((previous) => ({
            ...previous,
            [id]: new Map(outcomes.map((outcome) => [outcome.outcomeId, outcome])),
          }));
        } catch {
          // A window that cannot be read is a row of dashes, not a broken screen: the prices beside
          // it came from a different request and are still true.
        }
      })();
    }

    return () => controller.abort();
  }, [api, openIds, lastReadAt]);

  const toggle = (id: string) => {
    setExpanded((previous) =>
      previous.includes(id) ? previous.filter((open) => open !== id) : [...previous, id],
    );
    setChanges((previous) => (id in previous ? previous : { ...previous, [id]: null }));
  };

  const closeSheet = () => setSheet(null);

  const changed = (message: string) => {
    closeSheet();
    setNotice(message);
    refresh();
  };

  const freshness = refreshing
    ? "reading…"
    : lastReadAt === null
      ? "not read yet"
      : `updated ${formatAge(lastReadAt, now)}`;

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <h1 className={styles.heading}>Polymarket</h1>
          <div className={styles.headerActions}>
            {groups.length === 0 ? null : (
              <Button onClick={() => setSheet({ kind: "groups" })}>Groups</Button>
            )}
            <Button tone="primary" onClick={() => setSheet({ kind: "track" })}>
              Track event
            </Button>
          </div>
        </div>
        {/* The freshness line *is* the refresh control. A button that only refreshed would duplicate
            the poll and the pull gesture; this one says what the poll last managed, which is the part
            a throttled background tab makes worth saying. */}
        <button type="button" className={styles.freshness} onClick={refresh}>
          {freshness}
        </button>
      </header>

      {keys.length === 0 ? null : (
        <div className={styles.chips}>
          {keys.map((key) => {
            const on = enabled[key] !== false;
            return (
              <button
                key={key}
                type="button"
                className={[styles.chip, on ? styles.chipOn : styles.chipOff].join(" ")}
                aria-pressed={on}
                onClick={() => setEnabled((previous) => ({ ...previous, [key]: !on }))}
              >
                {labelFor(key)}
              </button>
            );
          })}
        </div>
      )}

      <div className={styles.scroller} ref={scroller}>
        {/* Follows the thumb and takes the list with it, so the gesture reads as the list moving
            rather than as a widget appearing over it. */}
        <div className={styles.pull} style={{ height: `${pull}px` }} aria-hidden>
          {pull > 0 ? (
            <span className={pull >= PULL_THRESHOLD ? styles.pullReady : styles.pullPending}>
              {pull >= PULL_THRESHOLD ? "release to refresh" : "pull to refresh"}
            </span>
          ) : null}
        </div>

        <main className={styles.list}>
          {notice === null ? null : (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          )}

          {error === null ? null : (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}

          {status === "loading" ? (
            <p className={styles.state} role="status">
              Reading the tracked events…
            </p>
          ) : status === "error" ? null : events.length === 0 ? (
            <p className={styles.state}>
              Nothing is under observation yet. Track an event to start collecting its prices.
            </p>
          ) : visible.length === 0 ? (
            <p className={styles.state}>Every group is switched off.</p>
          ) : (
            visible.map((section) => (
              <section key={section.key} className={styles.section}>
                <h2 className={styles.sectionTitle}>{section.label}</h2>
                {section.events.map((event) => (
                  <EventCard
                    key={event.providerEventId}
                    event={event}
                    expanded={expanded.includes(event.providerEventId)}
                    changes={changes[event.providerEventId] ?? null}
                    onToggle={() => toggle(event.providerEventId)}
                    onMove={() => setSheet({ kind: "move", event })}
                    onRemove={() => setSheet({ kind: "remove", event })}
                    now={now}
                  />
                ))}
              </section>
            ))
          )}
        </main>
      </div>

      {sheet?.kind === "track" ? (
        <TrackEventSheet
          api={api}
          groups={groupNames}
          onClose={closeSheet}
          onTracked={(title, alreadyTracked) => {
            closeSheet();
            setNotice(
              alreadyTracked
                ? `${title} was already under observation — nothing was collected twice.`
                : `${title} is under observation. Its first prices arrive within a minute.`,
            );
            refresh();
          }}
        />
      ) : null}

      {sheet?.kind === "move" ? (
        <MoveEventSheet
          api={api}
          event={sheet.event}
          groups={groups}
          onClose={closeSheet}
          onMoved={changed}
        />
      ) : null}

      {sheet?.kind === "groups" ? (
        <GroupsSheet api={api} groups={groups} onClose={closeSheet} onChanged={changed} />
      ) : null}

      {sheet?.kind === "remove" ? (
        <RemoveEventSheet
          api={api}
          event={sheet.event}
          onClose={closeSheet}
          onRemoved={(title) => {
            closeSheet();
            setNotice(`${title} and its collected history are gone.`);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}
