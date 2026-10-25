/** How the tab says numbers: an empty metric is a dash, never zero (`strategies-reports`), and Polish decimals. */

import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import type { Resolution } from "../data/types";
import type { RunItem } from "./strategiesApi";

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
