import {
  agentApi,
  type AgentApi,
  type AgentChartDrawing,
  type AgentDrawingPatch,
} from "./agentApi";

/**
 * One entry per symbol rather than per slot: a drawing belongs to the instrument, so two slots on US100 read the
 * same entry. Nothing is persisted, and a read replaces a symbol's whole list — the module is the record.
 */

export type DrawingsStatus = "loading" | "ready" | "error";

export interface SymbolDrawings {
  status: DrawingsStatus;
  drawings: readonly AgentChartDrawing[];
  /** What went wrong on the last read, kept beside whatever the chart is already
   *  drawing — a failed read never empties `drawings` (`terminal-chart` spec, "Nieudany
   *  odczyt obiektów"). */
  error: string | null;
}

export type DrawingsSnapshot = Readonly<Record<string, SymbolDrawings>>;

const EMPTY: SymbolDrawings = { status: "loading", drawings: [], error: null };

export interface DrawingsStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): DrawingsSnapshot;
  /** The entry for a symbol, loading it the first time anyone asks. Safe to call on every
   *  render: a symbol already loaded or already in flight costs nothing. */
  ensureLoaded(symbol: string): void;
  /** Read this symbol again, whether or not it was loaded. Answers what changed since
   *  the previous read, so the panel can say it in a sentence. */
  refresh(symbol: string): Promise<DrawingsChange>;
  /** Every symbol this store has an entry for, read again — what a finished turn needs,
   *  since the agent may have drawn on an instrument no slot is showing. */
  refreshAll(): Promise<DrawingsChange>;
  remove(id: number): Promise<string | null>;
  patch(id: number, patch: AgentDrawingPatch): Promise<string | null>;
}

/** What one read found that the previous one had not, and the other way round. Counted,
 *  not listed: the panel's sentence says how many appeared and how many went, and the
 *  chart itself is where the operator looks to see which. */
export interface DrawingsChange {
  added: number;
  removed: number;
}

const NO_CHANGE: DrawingsChange = { added: 0, removed: 0 };

function describeError(cause: unknown): string {
  return cause instanceof Error ? cause.message : "the agent module is not reachable";
}

function difference(
  before: readonly AgentChartDrawing[],
  after: readonly AgentChartDrawing[],
): DrawingsChange {
  const had = new Set(before.map((drawing) => drawing.id));
  const has = new Set(after.map((drawing) => drawing.id));
  return {
    added: after.filter((drawing) => !had.has(drawing.id)).length,
    removed: before.filter((drawing) => !has.has(drawing.id)).length,
  };
}

function sum(changes: readonly DrawingsChange[]): DrawingsChange {
  return changes.reduce(
    (total, change) => ({
      added: total.added + change.added,
      removed: total.removed + change.removed,
    }),
    NO_CHANGE,
  );
}

export function createDrawingsStore(api: AgentApi = agentApi): DrawingsStore {
  let snapshot: DrawingsSnapshot = {};
  const listeners = new Set<() => void>();
  const inFlight = new Set<string>();

  function commit(next: DrawingsSnapshot): void {
    snapshot = next;
    for (const listener of listeners) listener();
  }

  function put(symbol: string, entry: SymbolDrawings): void {
    commit({ ...snapshot, [symbol]: entry });
  }

  function entryFor(symbol: string): SymbolDrawings {
    return snapshot[symbol] ?? EMPTY;
  }

  /** The one place a symbol is read. Answers the difference so a caller can describe it;
   *  a failed read answers "nothing changed", because as far as anyone can tell nothing
   *  did. */
  async function read(symbol: string): Promise<DrawingsChange> {
    if (inFlight.has(symbol)) return NO_CHANGE;
    inFlight.add(symbol);
    const before = entryFor(symbol).drawings;
    try {
      const drawings = await api.listDrawings(symbol, new AbortController().signal);
      put(symbol, { status: "ready", drawings, error: null });
      return difference(before, drawings);
    } catch (cause) {
      // The previous list stays: a chart that empties itself because one read failed is
      // saying something untrue about the instrument.
      put(symbol, { status: "error", drawings: before, error: describeError(cause) });
      return NO_CHANGE;
    } finally {
      inFlight.delete(symbol);
    }
  }

  /** The operator's own write, applied by re-reading rather than by patching the copy in
   *  hand: the module is the record, and a locally-edited list that drifts from it is
   *  the failure mode this whole store exists under. Answers null on success and the
   *  sentence to show on failure. */
  async function write(symbol: string | null, act: () => Promise<unknown>): Promise<string | null> {
    try {
      await act();
    } catch (cause) {
      return describeError(cause);
    }
    if (symbol !== null) await read(symbol);
    return null;
  }

  function symbolOf(id: number): string | null {
    for (const [symbol, entry] of Object.entries(snapshot)) {
      if (entry.drawings.some((drawing) => drawing.id === id)) return symbol;
    }
    return null;
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => snapshot,
    ensureLoaded(symbol) {
      if (snapshot[symbol] !== undefined || inFlight.has(symbol)) return;
      put(symbol, EMPTY);
      void read(symbol);
    },
    refresh: (symbol) => read(symbol),
    async refreshAll() {
      const symbols = Object.keys(snapshot);
      return sum(await Promise.all(symbols.map((symbol) => read(symbol))));
    },
    remove(id) {
      const symbol = symbolOf(id);
      return write(symbol, () => api.deleteDrawing(id, new AbortController().signal));
    },
    patch(id, patch) {
      const symbol = symbolOf(id);
      return write(symbol, () => api.patchDrawing(id, patch, new AbortController().signal));
    },
  };
}

/** The sentence the panel shows after a turn, or null when the agent drew nothing. The
 *  same channel `describeChartControl` uses — a drawing appearing with no word about it
 *  is a change the operator cannot attribute to anyone's hand (`terminal-agent-chat`
 *  spec, "Panel MUST powiedzieć także o obiektach naniesionych i skasowanych"). */
export function describeDrawingsChange(change: DrawingsChange): string | null {
  const parts: string[] = [];
  if (change.added > 0) {
    parts.push(`drew ${change.added} ${change.added === 1 ? "object" : "objects"}`);
  }
  if (change.removed > 0) {
    parts.push(`removed ${change.removed}`);
  }
  if (parts.length === 0) return null;
  return `The agent ${parts.join(" and ")} on the chart.`;
}

export const drawingsStore = createDrawingsStore();
