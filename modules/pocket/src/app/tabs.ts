export const TABS = ["markets", "social", "news", "agent"] as const;

export type Tab = (typeof TABS)[number];

/** What the workbench's door says a person is (`GET /me`). A viewer reads the archive and does not talk to the agent. */
export type Role = "admin" | "viewer";

const VIEWER_TABS: readonly Tab[] = ["markets", "social", "news"];

export function tabsFor(role: Role): readonly Tab[] {
  return role === "viewer" ? VIEWER_TABS : TABS;
}

/** A remembered tab a role may not open becomes the first one it may: the stored value predates the role. */
export function allowedTab(tab: Tab, tabs: readonly Tab[]): Tab {
  return tabs.includes(tab) ? tab : (tabs[0] ?? "markets");
}

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
