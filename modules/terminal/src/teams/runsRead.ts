import type { TeamRun } from "./runs";

/** One team's runs, read in two places — the strip in the editor and the runs view — and
 *  so cached under one key: opening the runs from the strip draws the list already in
 *  hand rather than asking the module for it a second time. */
export function runsKey(teamId: number) {
  return ["teams", teamId, "runs"] as const;
}

/** Rendered before the first answer, and after one that failed. One identity, so a view
 *  waiting for its runs re-renders no more than a view that has them. */
export const NO_RUNS: TeamRun[] = [];
