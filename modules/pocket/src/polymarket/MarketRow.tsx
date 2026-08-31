import type { Market, OutcomeChanges } from "./api";
import { formatAge, formatProbability, isStale } from "./probability";
import { leadingOutcome } from "./ordering";
import { WindowChanges } from "./WindowChanges";
import { ProbBar } from "../ui/ProbBar";
import { Pill } from "../ui/Pill";
import styles from "./MarketRow.module.css";

export interface MarketRowProps {
  market: Market;
  /** This event's windows, keyed by outcome. Absent while they are still being read — the row shows
   *  the prices it already has rather than waiting for a second request. */
  changes: Map<number, OutcomeChanges> | null;
  now: Date;
}

export function MarketRow({ market, changes, now }: MarketRowProps) {
  const leading = leadingOutcome(market);
  const stale = leading !== undefined && isStale(leading.priceAt, now);

  return (
    <li className={styles.row}>
      <div className={styles.head}>
        <p className={styles.question}>{market.label ?? market.question}</p>
        {market.resolvedOutcome === null ? null : (
          <Pill tone="muted">{market.resolvedOutcome}</Pill>
        )}
      </div>

      <ul className={styles.outcomes}>
        {market.outcomes.map((outcome) => (
          <li key={outcome.id} className={styles.outcome}>
            <span className={styles.name}>{outcome.name}</span>
            <ProbBar price={outcome.price} compact />
            <span className={styles.price}>{formatProbability(outcome.price)}</span>
          </li>
        ))}
      </ul>

      <div className={styles.footer}>
        <WindowChanges changes={leading === undefined ? null : (changes?.get(leading.id) ?? null)} />
        {leading === undefined ? null : (
          <span className={stale ? styles.ageStale : styles.age}>
            {formatAge(leading.priceAt, now)}
          </span>
        )}
      </div>
    </li>
  );
}
