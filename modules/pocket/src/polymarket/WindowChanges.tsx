import type { OutcomeChanges, WindowName } from "./api";
import { directionOf, formatChange } from "./probability";
import styles from "./WindowChanges.module.css";

/** Four of the five the archive computes. `5m` is left out here and not elsewhere: on a phone the row
 *  has space for four, and five minutes of a prediction market is noise the operator does not act on. */
const SHOWN: WindowName[] = ["1h", "4h", "24h", "7d"];

const toneClass = {
  up: styles.up,
  down: styles.down,
  flat: styles.flat,
  none: styles.none,
} as const;

export function WindowChanges({ changes }: { changes: OutcomeChanges | null }) {
  return (
    <dl className={styles.windows}>
      {SHOWN.map((name) => {
        const found = changes?.windows.find((window) => window.window === name);
        const direction = directionOf(found?.change ?? null);
        return (
          <div key={name} className={styles.item}>
            <dt className={styles.label}>{name}</dt>
            {/* The reason a window is empty is the archive's answer, not a missing number, so it is
                carried on the element rather than dropped. */}
            <dd className={toneClass[direction]} title={found?.unavailable ?? undefined}>
              {changes === null ? "·" : formatChange(found?.change ?? null)}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
