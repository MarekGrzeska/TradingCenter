import type { AgentApi, AgentChartCommand, AgentChartSnapshot } from "./agentApi";
import { agentApi } from "./agentApi";
import { archive } from "../data/marketData";
import type { ArchiveAdmin } from "../data/source";
import { newIndicatorSelectionKey, type IndicatorSelection, type Resolution } from "../data/types";
import { gridStore, type GridStore } from "../grid/gridStore";

/** Where the terminal remembers what it has already applied. Its own key rather than a
 *  field of the grid config: the cursor is not part of what the operator arranged, and a
 *  grid config that failed to parse must not take the cursor down with it — that would
 *  replay a command the operator had already undone by hand. */
export const CHART_CURSOR_KEY = "terminal.agentChart.cursor.v1";

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

export interface ChartControlDeps {
  api: AgentApi;
  grid: GridStore;
  pairs: ArchiveAdmin;
  storage: Storage | null;
}

const DEFAULTS: ChartControlDeps = {
  api: agentApi,
  grid: gridStore,
  pairs: archive,
  storage: safeLocalStorage(),
};

function safeLocalStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function readCursor(storage: Storage | null): number {
  const raw = storage?.getItem(CHART_CURSOR_KEY);
  const parsed = raw === null || raw === undefined ? NaN : Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function writeCursor(storage: Storage | null, sequence: number): void {
  try {
    storage?.setItem(CHART_CURSOR_KEY, String(sequence));
  } catch {
    // A storage that refuses to write costs one replayed command on the next load, which
    // is a smaller price than the sync failing outright.
  }
}

/** What one applied command amounts to, in the words the panel puts on screen. Null when
 *  nothing was applied — either there was nothing new, or every part of it was refused. */
export interface ChartControlResult {
  applied: string[];
  skipped: string[];
}

function describeIndicators(command: AgentChartCommand): string {
  const drawn = command.indicators ?? [];
  if (drawn.length === 0) return "no indicators";
  return drawn
    .map((indicator) => {
      const params = Object.entries(indicator.params)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([name, value]) => `${name} ${value}`)
        .join(", ");
      return params === "" ? indicator.id.toUpperCase() : `${indicator.id.toUpperCase()} ${params}`;
    })
    .join(", ");
}

function toSelections(command: AgentChartCommand): IndicatorSelection[] {
  return (command.indicators ?? []).map((indicator) => ({
    // The key is the terminal's to hand out: the agent names what to draw, not which
    // instance of it this is.
    key: newIndicatorSelectionKey(),
    id: indicator.id,
    params: indicator.params,
    color: indicator.color,
  }));
}

/**
 * Reads whatever the agent set since the terminal last looked, applies it to the active
 * slot, and moves the cursor past it.
 *
 * The cursor moves even for a command that could not be applied whole. A command the
 * terminal refuses is not a command it should retry on every load — the agent was told
 * why at the time it asked (`agent-chart-control`, "Odmowa narzędzia nazywa, co
 * poprawić"), and this side says so once, to the operator.
 *
 * Failure to read is not failure to draw: a rejected read leaves the cursor, the chart
 * and the conversation exactly as they were (`terminal-agent-chat` spec, "Nieudany odczyt
 * poleceń MUST NOT przerywać rozmowy ani czyścić wykresu").
 */
export async function syncAgentChart(
  overrides: Partial<ChartControlDeps> = {},
): Promise<ChartControlResult | null> {
  const deps = { ...DEFAULTS, ...overrides };
  const cursor = readCursor(deps.storage);

  let command: AgentChartCommand | null;
  try {
    command = await deps.api.chartCommand(cursor, new AbortController().signal);
  } catch {
    return null;
  }
  if (command === null) return null;

  const applied: string[] = [];
  const skipped: string[] = [];
  const slotId = deps.grid.getSnapshot().activeSlot;
  const slot = deps.grid.getSnapshot().slots[slotId];

  let symbol = command.symbol;
  let resolution = command.resolution;

  if (symbol !== null || resolution !== null) {
    let allowed: Map<string, Resolution[]>;
    try {
      const pairs = await deps.pairs.listPairs(new AbortController().signal);
      allowed = new Map();
      for (const pair of pairs) {
        allowed.set(pair.symbol, [...(allowed.get(pair.symbol) ?? []), pair.resolution]);
      }
    } catch {
      // The archive could not say what it collects. Applying blind is what would put an
      // empty chart on screen, so the pair half of the command waits for the operator.
      return null;
    }

    const targetSymbol = symbol ?? slot.symbol;
    const targetResolution = (resolution ?? slot.resolution) as Resolution;
    const resolutions = targetSymbol === null ? undefined : allowed.get(targetSymbol);

    if (symbol !== null && resolutions === undefined) {
      skipped.push(`${symbol} is not collected`);
      symbol = null;
    }
    if (resolution !== null && (resolutions === undefined || !resolutions.includes(targetResolution))) {
      skipped.push(`${resolution} is not collected${targetSymbol ? ` for ${targetSymbol}` : ""}`);
      resolution = null;
    }
    // A symbol whose own collected resolutions do not include the slot's current one
    // would draw nothing either: the symbol arrives with the resolution it can be drawn
    // in, or not at all.
    if (symbol !== null && resolution === null && resolutions !== undefined) {
      if (!resolutions.includes(slot.resolution)) {
        skipped.push(`${symbol} is not collected at ${slot.resolution}`);
        symbol = null;
      }
    }
  }

  if (symbol !== null) {
    deps.grid.setSlotSymbol(slotId, symbol);
    applied.push(`symbol ${symbol}`);
  }
  if (resolution !== null) {
    deps.grid.setSlotResolution(slotId, resolution as Resolution);
    applied.push(`interval ${resolution}`);
  }
  if (command.indicators !== null) {
    deps.grid.setSlotIndicators(slotId, toSelections(command));
    applied.push(describeIndicators(command));
  }

  writeCursor(deps.storage, command.sequence);
  return { applied, skipped };
}

/** The sentence the panel shows, or null when there is nothing to say. */
export function describeChartControl(result: ChartControlResult | null): string | null {
  if (result === null) return null;
  if (result.applied.length === 0 && result.skipped.length === 0) return null;
  const parts: string[] = [];
  if (result.applied.length > 0) {
    parts.push(`The agent set the chart: ${result.applied.join("; ")}.`);
  }
  if (result.skipped.length > 0) {
    parts.push(`Not applied: ${result.skipped.join("; ")}.`);
  }
  return parts.join(" ");
}


/**
 * What the active slot is drawing, for the model to read as it answers. Null when the
 * slot has no instrument yet: "nothing is on screen" is better said by sending nothing
 * than by sending a snapshot full of nulls.
 */
export function activeChartSnapshot(grid: GridStore = gridStore): AgentChartSnapshot | null {
  const config = grid.getSnapshot();
  const slot = config.slots[config.activeSlot];
  if (slot.symbol === null) return null;
  return {
    symbol: slot.symbol,
    resolution: slot.resolution,
    indicators: slot.indicators.map((selection) => ({
      id: selection.id,
      params: selection.params,
      color: selection.color,
    })),
  };
}
