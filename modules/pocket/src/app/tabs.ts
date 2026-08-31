export const TABS = ["markets", "social", "agent"] as const;

export type Tab = (typeof TABS)[number];

const TAB_KEY = "pocket.tab.v1";

function isTab(value: unknown): value is Tab {
  return typeof value === "string" && (TABS as readonly string[]).includes(value);
}

/** Which screen the app opens on: the one it was last closed on. A phone is opened for seconds at a
 *  time, and landing on the wrong screen is a tap before every one of them. */
export function loadTab(storage: Pick<Storage, "getItem"> = localStorage): Tab {
  try {
    const stored = storage.getItem(TAB_KEY);
    return isTab(stored) ? stored : "markets";
  } catch {
    return "markets";
  }
}

export function saveTab(tab: Tab, storage: Pick<Storage, "setItem"> = localStorage): void {
  try {
    storage.setItem(TAB_KEY, tab);
  } catch {
    /* quota, or private mode — a remembered tab is not worth a broken screen */
  }
}
