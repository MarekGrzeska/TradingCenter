import { NavLink } from "react-router";
import { TABS } from "./tabs";

export function TabBar() {
  return (
    <nav className="flex h-10 shrink-0 items-center gap-1 border-b border-border bg-canvas px-4">
      {TABS.map((tab) => (
        <NavLink
          key={tab.id}
          to={`/${tab.path}`}
          className={({ isActive }) =>
            `rounded-t px-3 py-1.5 text-sm transition-colors ${
              isActive
                ? "border-b-2 border-primary bg-primary-soft text-ink"
                : "text-ink-muted hover:bg-panel-strong hover:text-ink"
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
