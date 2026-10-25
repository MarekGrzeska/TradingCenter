/**
 * The strategy the Strategies tab has open, for the panel to send with a turn (`agent-chat`, „Tura wie, którą strategię
 * operator ma otwartą”). Written by the tab while it is on screen and cleared when it leaves, so a question asked from
 * another tab carries none — the panel belongs to the terminal and reads whatever is set at the moment it sends.
 */

export interface AgentStrategyInView {
  strategyId: number | null;
  revision: number | null;
  /** The editor's text, only when it differs from `revision`. */
  draft: string | null;
}

/** The module's own ceiling (`STRATEGY_DRAFT_MAX_CHARS`): longer text is refused there, so it is not sent. */
export const STRATEGY_DRAFT_MAX_CHARS = 32_000;

let current: AgentStrategyInView | null = null;

export function setStrategyInView(view: AgentStrategyInView | null): void {
  current = view;
}

export function strategyInView(): AgentStrategyInView | null {
  if (current === null) return null;
  // Past the ceiling the module would refuse the whole turn; without the draft the model still reads the saved revision.
  if (current.draft !== null && current.draft.length > STRATEGY_DRAFT_MAX_CHARS) return { ...current, draft: null };
  return current;
}

export function strategyInViewToWire(view: AgentStrategyInView) {
  return { strategy_id: view.strategyId, revision: view.revision, draft: view.draft };
}
