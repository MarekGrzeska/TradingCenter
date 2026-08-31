import type { Tab } from "./tabs";
import styles from "./TabBar.module.css";

const LABELS: Record<Tab, string> = { markets: "Markets", agent: "Agent" };

/** At the bottom, because that is where a thumb is. A row of tabs at the top of a phone screen is a
 *  reach for every switch, and this app is opened for seconds at a time. */
export function TabBar({
  current,
  onChange,
}: {
  current: Tab;
  onChange: (tab: Tab) => void;
}) {
  return (
    <nav className={styles.bar} aria-label="Screens">
      {(Object.keys(LABELS) as Tab[]).map((tab) => (
        <button
          key={tab}
          type="button"
          className={tab === current ? styles.on : styles.off}
          // Not `aria-selected`, which belongs to a tablist: these switch the whole screen, and a
          // screen reader should hear which one is current rather than which one is selected.
          aria-current={tab === current ? "page" : undefined}
          onClick={() => onChange(tab)}
        >
          <span className={styles.icon} aria-hidden>
            {tab === "markets" ? (
              <svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor">
                <path
                  d="M3 14.5 7.5 9.5 11 12.5 17 5.5"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor">
                <path
                  d="M3.5 5.5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8l-4.5 3.5z"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </span>
          {LABELS[tab]}
        </button>
      ))}
    </nav>
  );
}
