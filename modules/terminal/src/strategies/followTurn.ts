/**
 * What the tab does once a turn of the agent ends (`terminal-strategies`, „Zakładka współpracuje z panelem agenta”). The
 * editor never loses the operator's unsaved text to a revision the agent saved; with nothing unsaved, it shows the agent's.
 */

import type { StrategyItem } from "./strategiesApi";

export interface EditorAt {
  strategyId: number | null;
  /** The revision the editor's text was loaded from; null for a new strategy not saved yet. */
  base: number | null;
  dirty: boolean;
}

export type AfterTurn =
  | { kind: "none" }
  | { kind: "load"; revision: number }
  | { kind: "newer"; revision: number };

export function afterTurn(editor: EditorAt, latest: number | null): AfterTurn {
  if (editor.strategyId === null || editor.base === null || latest === null || latest <= editor.base) {
    return { kind: "none" };
  }
  return editor.dirty ? { kind: "newer", revision: latest } : { kind: "load", revision: latest };
}

/** The strategy the agent created during a turn, to open when the tab had none open; null otherwise. */
export function createdDuringTurn(knownBefore: ReadonlySet<number>, now: readonly StrategyItem[], hadOneOpen: boolean): number | null {
  if (hadOneOpen) return null;
  const created = now.filter((s) => !knownBefore.has(s.id) && s.latestAuthor === "agent");
  if (created.length === 0) return null;
  return created.reduce((newest, s) => (s.changedAt > newest.changedAt ? s : newest)).id;
}

/** The text an editor shows for a document: what is stored, two-space indented, so a reload reads like the save. */
export function documentText(document: unknown): string {
  return JSON.stringify(document, null, 2);
}
