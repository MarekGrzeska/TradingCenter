import { lazy, type ComponentType } from "react";
import { AccountsView } from "../accounts/AccountsView";
import { AlertsView } from "../alerts/AlertsView";
import { AgentSettingsView } from "../agent/settings/AgentSettingsView";
import { CollectionHistoryView } from "../history/CollectionHistoryView";
import { GridView } from "../grid/GridView";
import { InstrumentsView } from "../instruments/InstrumentsView";
import { NewsView } from "../news/NewsView";
import { PolymarketView } from "../polymarket/PolymarketView";
import { SocialView } from "../social/SocialView";
import { TeamsView } from "../teams/TeamsView";
import { TelegramView } from "../telegram/TelegramView";
import { UsersView } from "../users/UsersView";
import { YoutubeView } from "../youtube/YoutubeView";

/**
 * The one place tabs are declared — routing and the nav bar are both derived from it. `Archive` is gone rather than
 * renamed, so a stale bookmark falls through to the unknown-tab page instead of a silent redirect.
 */
// Loaded when first opened: its editor is a dependency no other tab pays for (design D9 of the strategies' stage 2).
const StrategiesView = lazy(() => import("../strategies/StrategiesView").then((m) => ({ default: m.StrategiesView })));

export const TAB_GROUPS = [
  { id: "trading", label: "Trading" },
  { id: "data", label: "Data" },
  { id: "messaging", label: "Messaging" },
  { id: "settings", label: "Settings" },
] as const;

export type TabGroupId = (typeof TAB_GROUPS)[number]["id"];

export interface TabDefinition {
  id: string;
  label: string;
  group: TabGroupId;
  path: string;
  Component: ComponentType;
}

export const TABS: TabDefinition[] = [
  {
    id: "graph",
    label: "Graph",
    group: "trading",
    path: "graph",
    Component: GridView,
  },
  {
    id: "instruments",
    label: "Instruments",
    group: "trading",
    path: "instruments",
    Component: InstrumentsView,
  },
  {
    id: "teams",
    label: "Teams",
    group: "trading",
    path: "teams",
    Component: TeamsView,
  },
  {
    id: "strategies",
    label: "Strategies",
    group: "trading",
    path: "strategies",
    Component: StrategiesView,
  },
  {
    id: "accounts",
    label: "Accounts",
    group: "trading",
    path: "accounts",
    Component: AccountsView,
  },
  {
    id: "data-history",
    label: "Data History",
    group: "data",
    path: "data-history",
    Component: CollectionHistoryView,
  },
  {
    id: "polymarket",
    label: "Polymarket",
    group: "data",
    path: "polymarket",
    Component: PolymarketView,
  },
  {
    id: "social",
    label: "Social",
    group: "data",
    path: "social",
    Component: SocialView,
  },
  {
    id: "news",
    label: "News",
    group: "data",
    path: "news",
    Component: NewsView,
  },
  {
    id: "youtube",
    label: "YouTube",
    group: "data",
    path: "youtube",
    Component: YoutubeView,
  },
  {
    id: "alerts",
    label: "Alerts",
    group: "messaging",
    path: "alerts",
    Component: AlertsView,
  },
  {
    id: "telegram",
    label: "Telegram",
    group: "messaging",
    path: "telegram",
    Component: TelegramView,
  },
  {
    id: "agent-settings",
    label: "Agent Settings",
    group: "settings",
    path: "agent-settings",
    Component: AgentSettingsView,
  },
  {
    id: "users",
    label: "Users",
    group: "settings",
    path: "users",
    Component: UsersView,
  },
];

export const DEFAULT_TAB_PATH = "graph";
