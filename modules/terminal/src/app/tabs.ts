import type { ComponentType } from "react";
import { GridView } from "../grid/GridView";
import { InstrumentsView } from "../instruments/InstrumentsView";

/**
 * The one place tabs are declared — routing and the nav bar are both derived
 * from this list, so adding a tab is an entry here, not a change to either.
 * terminal-shell spec, "Rejestr zakładek jest otwarty".
 *
 * `Archive` is gone rather than renamed: `Instruments` absorbed it, so a
 * stale `/archive` bookmark falls through to the unknown-tab page rather than
 * a silent redirect (design.md, "Zakładki: `Archive` znika, `Data History`
 * dochodzi"). `Positions`, `Orders` and `Account` are `coming-soon` for the
 * life of this change — see proposal.md.
 */
export type TabStatus = "ready" | "coming-soon";

export interface ReadyTab {
  id: string;
  label: string;
  path: string;
  status: "ready";
  Component: ComponentType;
}

export interface ComingSoonTab {
  id: string;
  label: string;
  path: string;
  status: "coming-soon";
}

export type TabDefinition = ReadyTab | ComingSoonTab;

export const TABS: TabDefinition[] = [
  { id: "graph", label: "Graph", path: "graph", status: "ready", Component: GridView },
  {
    id: "instruments",
    label: "Instruments",
    path: "instruments",
    status: "ready",
    Component: InstrumentsView,
  },
  { id: "positions", label: "Positions", path: "positions", status: "coming-soon" },
  { id: "orders", label: "Orders", path: "orders", status: "coming-soon" },
  { id: "account", label: "Account", path: "account", status: "coming-soon" },
];

export const DEFAULT_TAB_PATH = "graph";
