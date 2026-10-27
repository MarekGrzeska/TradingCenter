/** How the two tabs order what they list: strategies grouped by instrument and interval, runs by a column picked. */

import { RESOLUTION_SECONDS } from "../chart/chartWindow";
import type { Resolution } from "../data/types";
import { interval } from "./present";
import type { RunItem, StrategyItem } from "./strategiesApi";

export interface StrategyGroup {
  key: string;
  symbol: string;
  timeframe: string;
  strategies: { item: StrategyItem; shortName: string }[];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The name without the "US100 M5 — " its group header already says; a name that is nothing else stays whole. */
export function shortName(item: StrategyItem): string {
  const prefix = new RegExp(`^${escape(item.symbol)}\\s+${escape(interval(item.timeframe))}\\s*[—–-]\\s*`, "i");
  const rest = item.name.replace(prefix, "");
  return rest === "" ? item.name : rest;
}

/** Groups by instrument, then by interval from the shortest; inside a group the last changed first. */
export function groupStrategies(items: readonly StrategyItem[], query = ""): StrategyGroup[] {
  const needle = query.trim().toLocaleLowerCase("pl");
  const groups = new Map<string, StrategyGroup>();
  for (const item of items) {
    if (needle !== "" && !item.name.toLocaleLowerCase("pl").includes(needle)) continue;
    const key = `${item.symbol}|${item.timeframe}`;
    const group = groups.get(key) ?? { key, symbol: item.symbol, timeframe: item.timeframe, strategies: [] };
    group.strategies.push({ item, shortName: shortName(item) });
    groups.set(key, group);
  }
  const seconds = (timeframe: string) => RESOLUTION_SECONDS[timeframe as Resolution] ?? Number.MAX_SAFE_INTEGER;
  for (const group of groups.values()) group.strategies.sort((a, b) => b.item.changedAt.getTime() - a.item.changedAt.getTime());
  return [...groups.values()].sort((a, b) => a.symbol.localeCompare(b.symbol) || seconds(a.timeframe) - seconds(b.timeframe));
}

/** "1 próba", "3 próby", "5 prób". */
export function trials(count: number): string {
  const few = count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 12 || count % 100 > 14);
  return `${count} ${count === 1 ? "próba" : few ? "próby" : "prób"}`;
}

export type RunSortKey =
  | "id"
  | "strategy"
  | "status"
  | "revision"
  | "from"
  | "requestedBy"
  | "trades"
  | "returnPct"
  | "totalR"
  | "expectancyR"
  | "maxDrawdownR"
  | "sharpe";

export interface RunSort {
  key: RunSortKey;
  descending: boolean;
}

/** Numbers start from the largest, words from A; a second click turns it. */
export function nextSort(current: RunSort | null, key: RunSortKey): RunSort {
  if (current?.key === key) return { key, descending: !current.descending };
  return { key, descending: !["strategy", "status", "requestedBy"].includes(key) };
}

function valueOf(run: RunItem, key: RunSortKey, names: ReadonlyMap<number, string>): number | string | null {
  switch (key) {
    case "id":
      return run.id;
    case "strategy":
      return names.get(run.strategyId) ?? null;
    case "status":
      return run.status;
    case "revision":
      return run.revision;
    case "from":
      return run.from.getTime();
    case "requestedBy":
      return run.requestedBy;
    default:
      return run.headline?.[key] ?? null;
  }
}

/** A run with nothing in the column goes last whichever way the column is turned — a dash is not a small number. */
export function sortRuns(runs: readonly RunItem[], sort: RunSort | null, names: ReadonlyMap<number, string> = new Map()): RunItem[] {
  if (sort === null) return [...runs];
  const sign = sort.descending ? -1 : 1;
  return [...runs].sort((a, b) => {
    const x = valueOf(a, sort.key, names);
    const y = valueOf(b, sort.key, names);
    if (x === null || y === null) return x === y ? b.id - a.id : x === null ? 1 : -1;
    const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pl");
    return order === 0 ? b.id - a.id : sign * order;
  });
}
