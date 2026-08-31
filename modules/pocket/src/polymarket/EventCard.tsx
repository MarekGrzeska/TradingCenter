import { useId } from "react";
import type { OutcomeChanges, TrackedEvent } from "./api";
import { headlineMarket, leadingOutcome, marketsForDisplay } from "./ordering";
import { formatProbability } from "./probability";
import { MarketRow } from "./MarketRow";
import { ProbBar } from "../ui/ProbBar";
import { Pill, type PillTone } from "../ui/Pill";
import styles from "./EventCard.module.css";

const COLLECTION_TONE: Record<TrackedEvent["collection"]["state"], PillTone> = {
  collecting: "ok",
  stalled: "warn",
  resolved: "muted",
};

export interface EventCardProps {
  event: TrackedEvent;
  expanded: boolean;
  /** This event's windows, or `null` while they are still being read. */
  changes: Map<number, OutcomeChanges> | null;
  onToggle: () => void;
  onRemove: () => void;
  now: Date;
}

export function EventCard({ event, expanded, changes, onToggle, onRemove, now }: EventCardProps) {
  const listId = useId();
  const headline = headlineMarket(event);
  const headlineOutcome = headline === undefined ? undefined : leadingOutcome(headline);
  const markets = marketsForDisplay(event.markets);

  return (
    <article className={styles.card}>
      {/* The whole header is the control, not a chevron beside it: a 24px target is a miss on a
          phone, and there is nothing else in this row to tap. */}
      <button
        type="button"
        className={styles.header}
        aria-expanded={expanded}
        aria-controls={expanded ? listId : undefined}
        onClick={onToggle}
      >
        <span className={styles.headerText}>
          <span className={styles.title}>{event.title}</span>
          <span className={styles.meta}>
            <Pill tone={COLLECTION_TONE[event.collection.state]}>{event.collection.state}</Pill>
            {event.group === null ? null : <span className={styles.group}>{event.group}</span>}
            <span className={styles.count}>
              {event.markets.length} {event.markets.length === 1 ? "market" : "markets"}
            </span>
          </span>
        </span>
        <span className={expanded ? styles.chevronOpen : styles.chevron} aria-hidden>
          <svg viewBox="0 0 12 12" width="14" height="14">
            <path
              d="M2.5 4.5 6 8 9.5 4.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>

      {headline === undefined || headlineOutcome === undefined ? null : (
        <div className={styles.headline}>
          <div className={styles.headlineText}>
            <span className={styles.headlineName}>
              {headline.label ?? headlineOutcome.name}
            </span>
            <span className={styles.headlinePrice}>
              {formatProbability(headlineOutcome.price)}
            </span>
          </div>
          <ProbBar price={headlineOutcome.price} />
        </div>
      )}

      {event.collection.state === "stalled" && event.collection.reason !== null ? (
        <p className={styles.reason}>{event.collection.reason}</p>
      ) : null}

      {/* Rendered only while open, not hidden with an attribute: one measured event holds 128
          markets, and a phone that lays out every row of every collapsed card scrolls badly. */}
      {!expanded ? null : (
        <div id={listId}>
          <ul className={styles.markets}>
            {markets.map((market) => (
              <MarketRow key={market.id} market={market} changes={changes} now={now} />
            ))}
          </ul>

          <div className={styles.actions}>
            <a className={styles.link} href={event.url} target="_blank" rel="noreferrer noopener">
              Open on polymarket.com
            </a>
            <button type="button" className={styles.remove} onClick={onRemove}>
              Remove
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
