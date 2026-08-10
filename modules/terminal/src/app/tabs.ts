import type { ComponentType } from "react";
import { CollectionHistoryView } from "../history/CollectionHistoryView";
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
 * dochodzi"). Every entry here has a view — a tab with none does not belong
 * in the registry (terminal-shell spec, "Rejestr zakładek jest otwarty").
 */
export interface TabDefinition {
  id: string;
  label: string;
  path: string;
  Component: ComponentType;
}

export const TABS: TabDefinition[] = [
  { id: "graph", label: "Graph", path: "graph", Component: GridView },
  { id: "instruments", label: "Instruments", path: "instruments", Component: InstrumentsView },
  {
    id: "data-history",
    label: "Data History",
    path: "data-history",
    Component: CollectionHistoryView,
  },
];

export const DEFAULT_TAB_PATH = "graph";
