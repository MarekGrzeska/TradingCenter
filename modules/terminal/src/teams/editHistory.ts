import type { TeamDefinition, TeamLayout } from "./teamsApi";

/** What one step back restores: the team as it was drawn *and* where it was drawn. A move
 *  is an action like any other, so undoing one has to put the node back. */
export interface TeamState {
  definition: TeamDefinition;
  places: TeamLayout;
}

export interface HistoryEntry {
  state: TeamState;
  /** What kind of action pushed this entry. Kinds beginning with `text:` coalesce with the
   *  one before them — see `remember`. */
  kind: string;
}

export type EditHistory = HistoryEntry[];

export const NO_HISTORY: EditHistory = [];

/** How far back the tab remembers. A bound rather than a promise: every entry holds a whole
 *  definition, and a team being typed into produces one per burst of typing. Fifty is far
 *  more than the "I did not mean that" this exists for, and it is not a save log — what is
 *  saved is in the module, with its own version. */
const DEPTH = 50;

/**
 * The state *before* an action, so it can be taken back. Text edits coalesce — `edit` runs on every keystroke —
 * so undo gives back what the operator had before they started typing; every other kind always pushes.
 */
export function remember(history: EditHistory, before: TeamState, kind: string): EditHistory {
  const top = history[history.length - 1];
  if (top !== undefined && kind.startsWith("text:") && top.kind === kind) return history;
  return [...history, { state: before, kind }].slice(-DEPTH);
}

/** The state to go back to and the history that remains, or `null` when there is nothing
 *  to take back. */
export function undo(history: EditHistory): { state: TeamState; history: EditHistory } | null {
  const top = history[history.length - 1];
  if (top === undefined) return null;
  return { state: top.state, history: history.slice(0, -1) };
}

/** The kind for a change to one agent's fields: text if it only touches what is typed,
 *  and a plain action otherwise. Picking a model or ticking a tool is one click and one
 *  step back, so neither coalesces with anything. */
export function kindForPatch(agentKey: string, patch: object): string {
  const typed = ["role", "prompt", "guidance"];
  const keys = Object.keys(patch);
  return keys.every((key) => typed.includes(key))
    ? `text:${agentKey}:${keys.join(",")}`
    : `agent:${agentKey}`;
}
