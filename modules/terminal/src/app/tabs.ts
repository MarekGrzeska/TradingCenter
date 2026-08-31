import type { ComponentType } from "react";
import { AccountsView } from "../accounts/AccountsView";
import { AgentSettingsView } from "../agent/settings/AgentSettingsView";
import { CollectionHistoryView } from "../history/CollectionHistoryView";
import { GridView } from "../grid/GridView";
import { InstrumentsView } from "../instruments/InstrumentsView";
import { PolymarketView } from "../polymarket/PolymarketView";
import { SocialView } from "../social/SocialView";
import { StrategyView } from "../strategy/StrategyView";
import { TeamsView } from "../teams/TeamsView";

/**
 * The one place tabs are declared — routing and the nav bar are both derived from it. `Archive` is gone rather than
 * renamed, so a stale bookmark falls through to the unknown-tab page instead of a silent redirect.
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
  { id: "teams", label: "Teams", path: "teams", Component: TeamsView },
  { id: "polymarket", label: "Polymarket", path: "polymarket", Component: PolymarketView },
  { id: "social", label: "Social", path: "social", Component: SocialView },
  { id: "strategy", label: "Strategie", path: "strategy", Component: StrategyView },
  { id: "accounts", label: "Accounts", path: "accounts", Component: AccountsView },
  {
    id: "agent-settings",
    label: "Agent Settings",
    path: "agent-settings",
    Component: AgentSettingsView,
  },
];

export const DEFAULT_TAB_PATH = "graph";
