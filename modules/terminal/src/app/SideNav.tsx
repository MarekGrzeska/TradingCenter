import { useState } from "react";
import { NavLink, useLocation } from "react-router";
import { SourceStatus } from "./SourceStatus";
import { TABS, TAB_GROUPS, type TabGroupId } from "./tabs";

/** Tabs grouped by `group` in `TAB_GROUPS` order: a new tab is one registry entry, never a new row of chrome. */
export function SideNav() {
  const { pathname } = useLocation();
  const routeGroup = TABS.find((tab) => `/${tab.path}` === pathname)?.group ?? null;

  // One group open at a time. Following the route re-opens its group when the address moves from outside the
  // nav (a link in a view, the back button); adjusting state during render avoids a frame of the wrong group.
  const [open, setOpen] = useState<TabGroupId | null>(routeGroup);
  const [seenRouteGroup, setSeenRouteGroup] = useState(routeGroup);
  if (routeGroup !== seenRouteGroup) {
    setSeenRouteGroup(routeGroup);
    if (routeGroup) setOpen(routeGroup);
  }

  return (
    <nav
      aria-label="Main"
      className="flex w-48 shrink-0 flex-col gap-1 overflow-y-auto border-r border-border bg-canvas px-2 py-3"
    >
      <span className="flex items-baseline gap-1.5 px-3 pb-2 text-sm font-semibold">
        <span className="text-ink">TradingCenter</span>
        <span className="text-secondary">Terminal</span>
      </span>
      {TAB_GROUPS.map((group) => {
        const tabs = TABS.filter((tab) => tab.group === group.id);
        if (tabs.length === 0) return null;
        const expanded = open === group.id;
        return (
          <section key={group.id} aria-label={group.label} className="flex flex-col gap-0.5">
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : group.id)}
              className="flex items-center justify-between rounded px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-ink-muted transition-colors hover:bg-panel-strong hover:text-ink"
            >
              {group.label}
              <span aria-hidden className={`transition-transform ${expanded ? "rotate-90" : ""}`}>
                ›
              </span>
            </button>
            {expanded &&
              tabs.map((tab) => (
                <NavLink
                  key={tab.id}
                  to={`/${tab.path}`}
                  className={({ isActive }) =>
                    `ml-2 rounded border-l-2 px-3 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "border-primary bg-primary-soft text-ink"
                        : "border-transparent text-ink-muted hover:bg-panel-strong hover:text-ink"
                    }`
                  }
                >
                  {tab.label}
                </NavLink>
              ))}
          </section>
        );
      })}
      <SourceStatus />
    </nav>
  );
}
