import { bandFor } from "../polymarket/probability";
import styles from "./ProbBar.module.css";

export interface ProbBarProps {
  /** The probability on 0..1, or `null` when nothing has been collected — which draws an empty
   *  track rather than a zero-width bar, because those two look the same and mean opposite things. */
  price: number | null;
  compact?: boolean;
}

/** A probability as a length and a colour. Both say the same thing on purpose: a column of these is
 *  scanned, and length alone is hard to read at a glance on a phone held at arm's length. */
export function ProbBar({ price, compact }: ProbBarProps) {
  const band = bandFor(price);
  const width = price === null ? 0 : Math.min(100, Math.max(0, price * 100));

  return (
    <div
      className={[styles.track, compact ? styles.compact : ""].filter(Boolean).join(" ")}
      role="img"
      aria-label={
        band === null ? "no price collected" : `${Math.round(width)} percent, ${band.reading}`
      }
    >
      {band === null ? null : (
        <div className={styles.fill} style={{ width: `${width}%`, background: band.fill }} />
      )}
    </div>
  );
}
