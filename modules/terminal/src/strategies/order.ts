/** How the two tabs order and narrow what they list: strategies grouped by instrument and interval, runs by a column
 *  picked and by the filters above them. */

import { RESOLUTION_SECONDS } from "../chart/chartWindow";
import type { Resolution } from "../data/types";
import { formatInstant } from "../ui/formatTime";
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

const seconds = (timeframe: string) => RESOLUTION_SECONDS[timeframe as Resolution] ?? Number.MAX_SAFE_INTEGER;
const named = (name: string, query: string) => name.toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl"));

/** The intervals the strategies are written for, from the shortest — what an interval filter offers. */
export function timeframesOf(items: readonly StrategyItem[]): string[] {
  return [...new Set(items.map((item) => item.timeframe))].sort((a, b) => seconds(a) - seconds(b));
}

/** Groups by instrument, then by interval from the shortest; inside a group the last changed first. An empty `timeframe`
 *  keeps every interval. */
export function groupStrategies(items: readonly StrategyItem[], query = "", timeframe = ""): StrategyGroup[] {
  const groups = new Map<string, StrategyGroup>();
  for (const item of items) {
    if (!named(item.name, query) || (timeframe !== "" && item.timeframe !== timeframe)) continue;
    const key = `${item.symbol}|${item.timeframe}`;
    const group = groups.get(key) ?? { key, symbol: item.symbol, timeframe: item.timeframe, strategies: [] };
    group.strategies.push({ item, shortName: shortName(item) });
    groups.set(key, group);
  }
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
  | "annualReturnPct"
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

/** What the operator typed above the runs, as typed: an empty field narrows nothing. Days are `<input type="date">`'s,
 *  percent is in percent. */
export interface RunFilter {
  name: string;
  timeframe: string;
  from: string;
  to: string;
  minTrades: string;
  minAnnualReturnPct: string;
  minSharpe: string;
}

export const NO_RUN_FILTER: RunFilter = {
  name: "",
  timeframe: "",
  from: "",
  to: "",
  minTrades: "",
  minAnnualReturnPct: "",
  minSharpe: "",
};

export const runFilterActive = (filter: RunFilter) => Object.values(filter).some((value) => value.trim() !== "");

/** A Polish decimal comma is a decimal; anything that is not a number narrows nothing rather than everything. */
function threshold(typed: string): number | null {
  const value = Number(typed.trim().replace(",", "."));
  return typed.trim() === "" || !Number.isFinite(value) ? null : value;
}

const day = (d: Date) => formatInstant(d.getTime() / 1000).slice(0, 10);

/** Runs whose strategy matches by name and interval, whose tested range lies within the days given, and whose results
 *  reach every minimum given — a run with no number in a column a minimum is set on does not reach it. */
export function filterRuns(runs: readonly RunItem[], filter: RunFilter, strategies: readonly StrategyItem[]): RunItem[] {
  const byId = new Map(strategies.map((s) => [s.id, s]));
  const minTrades = threshold(filter.minTrades);
  const minAnnual = threshold(filter.minAnnualReturnPct);
  const minSharpe = threshold(filter.minSharpe);
  const reaches = (value: number | null | undefined, min: number | null) => min === null || (value != null && value >= min);
  return runs.filter((run) => {
    const strategy = byId.get(run.strategyId);
    if (filter.name.trim() !== "" && (strategy === undefined || !named(strategy.name, filter.name))) return false;
    if (filter.timeframe !== "" && strategy?.timeframe !== filter.timeframe) return false;
    if (filter.from !== "" && day(run.from) < filter.from) return false;
    if (filter.to !== "" && day(run.to) > filter.to) return false;
    return (
      reaches(run.headline?.trades, minTrades) &&
      reaches(run.headline?.annualReturnPct, minAnnual === null ? null : minAnnual / 100) &&
      reaches(run.headline?.sharpe, minSharpe)
    );
  });
}
