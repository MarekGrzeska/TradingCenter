/** How the tab says numbers: an empty metric is a dash, never zero (`strategies-reports`), and Polish decimals. */

import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import type { Resolution } from "../data/types";
import { formatInstant } from "../ui/formatTime";
import type { CostProfile, CostsSource, RunItem } from "./strategiesApi";

const NUMBER = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 });
const PERCENT = new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 2 });

export const EMPTY = "—";

export function num(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : NUMBER.format(value);
}

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : PERCENT.format(value);
}

export function r(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : `${NUMBER.format(value)} R`;
}

export function interval(wire: string): string {
  return RESOLUTION_LABEL[wire as Resolution] ?? wire;
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "w kolejce",
  running: "liczy się",
  done: "gotowe",
  failed: "nieudane",
  cancelled: "anulowane",
};

export const EXIT_LABEL: Record<string, string> = {
  stop: "stop",
  target: "cel",
  trail: "stop kroczący",
  when: "warunek wyjścia",
  max_bars: "limit świec",
  out_of_capital: "brak kapitału",
  end_of_range: "koniec zakresu",
};

/** Minutes a range holds, as the package counts them against its ceiling — calendar minutes, weekends included. */
export function minutesIn(from: Date, to: Date): number {
  return Math.max(0, Math.floor((to.getTime() - from.getTime()) / 60_000));
}

/** Whether the list has to keep asking: only while something waits or computes, so an idle tab costs nothing. */
export function anyPending(runs: readonly RunItem[]): boolean {
  return runs.some((run) => run.status === "queued" || run.status === "running");
}

/** Where a run's costs came from; a run without them is said to be one, not shown as zeros. */
export const COSTS_SOURCE_LABEL: Record<CostsSource, string> = {
  request: "wpisane do uruchomienia",
  broker: "z capital.com",
  operator: "z profilu operatora",
  none: "bez kosztów",
};

export const WITHOUT_COSTS_NOTE = "bez kosztów — wynik pomija spread, poślizg i finansowanie";

/** Where the costs a form shows came from, in the operator's words. */
export function sourceLabel(profile: CostProfile): string {
  if (profile.source === "operator") return "z profilu wpisanego przez operatora";
  const at = profile.fetchedAt === null ? "" : `, pobrane ${formatInstant(profile.fetchedAt.getTime() / 1000)}`;
  return `z capital.com${at}`;
}
