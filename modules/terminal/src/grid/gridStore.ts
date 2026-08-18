import { safeLocalStorage } from "../data/storage";
import {
  defaultGridConfig,
  parseGridConfig,
  type GridConfig,
  type LayoutId,
  type SlotId,
} from "./model";
import type { ChartFocusRequest, IndicatorSelection, Resolution, VisibleTimeRange } from "../data/types";

/** Versioned so a future shape change is a clean miss (defaults) rather than a
 *  half-understood read — terminal-grid spec, "Zapisany stan jest nieczytelny". */
export const STORAGE_KEY = "terminal.grid.v1";

export interface GridStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): GridConfig;
  setLayout(layout: LayoutId): void;
  setActiveSlot(slot: SlotId): void;
  setSlotSymbol(slot: SlotId, symbol: string): void;
  /** Empty a slot back to "pick an instrument". The empty state is otherwise
   *  only reachable on a fresh install, which would make it unreachable in
   *  practice. */
  clearSlotSymbol(slot: SlotId): void;
  setSlotResolution(slot: SlotId, resolution: Resolution): void;
  setSlotIndicators(slot: SlotId, indicators: IndicatorSelection[]): void;
  /** A one-off "show this fragment of the axis" for a slot — transient, never written to
   *  storage, and on its own subscription so setting it does not fire every listener
   *  watching the persisted config (`terminal-chart`, "Wykres przyjmuje kadr z
   *  zewnątrz"). */
  subscribeFocusRequest(listener: () => void): () => void;
  getFocusRequest(slot: SlotId): ChartFocusRequest | null;
  setFocusRequest(slot: SlotId, focus: ChartFocusRequest): void;
  /** Consumed once applied — or once given up on. A request nobody clears would replay
   *  itself on the next unrelated re-render. */
  clearFocusRequest(slot: SlotId): void;
  /** What a slot's chart last reported as visible — written by `Chart`'s own
   *  `onVisibleRangeChange` on every pan and zoom, read only when a turn is about to ask
   *  a question. No subscription at all, unlike the focus request above: nothing needs
   *  to react to this changing, only to read whatever it last held (design.md, "kadr
   *  reaktywny, widok nie") — a `subscribe` nobody calls is a `subscribe` that does not
   *  belong here. */
  getVisibleRange(slot: SlotId): VisibleTimeRange | null;
  setVisibleRange(slot: SlotId, range: VisibleTimeRange | null): void;
}

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

function load(storage: Storage | null): GridConfig {
  if (!storage) return defaultGridConfig();
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return defaultGridConfig();
    return parseGridConfig(JSON.parse(raw)) ?? defaultGridConfig();
  } catch {
    // Unparseable JSON, or a storage that throws (Safari private mode) — the
    // terminal still has to start.
    return defaultGridConfig();
  }
}

export function createGridStore(storage: Storage | null = safeLocalStorage()): GridStore {
  let config = load(storage);
  const listeners = new Set<() => void>();
  // Kept outside `config` on purpose: it must not be written to storage and must not
  // wake a listener that only cares about the persisted layout.
  const focusRequests = new Map<SlotId, ChartFocusRequest>();
  const focusListeners = new Set<() => void>();
  const visibleRanges = new Map<SlotId, VisibleTimeRange>();

  function commit(next: GridConfig): void {
    config = next;
    try {
      storage?.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // A full or unavailable quota must not break the interaction that
      // triggered the save; the config simply won't outlive this session.
    }
    for (const listener of listeners) listener();
  }

  function updateSlot(slot: SlotId, patch: Partial<GridConfig["slots"][SlotId]>): void {
    commit({
      ...config,
      slots: { ...config.slots, [slot]: { ...config.slots[slot], ...patch } },
    });
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => config,
    setLayout(layout) {
      if (layout === config.layout) return;
      commit({ ...config, layout });
    },
    setActiveSlot(slot) {
      if (slot === config.activeSlot) return;
      commit({ ...config, activeSlot: slot });
    },
    setSlotSymbol(slot, symbol) {
      updateSlot(slot, { symbol });
    },
    clearSlotSymbol(slot) {
      updateSlot(slot, { symbol: null });
    },
    setSlotResolution(slot, resolution) {
      updateSlot(slot, { resolution });
    },
    setSlotIndicators(slot, indicators) {
      updateSlot(slot, { indicators });
    },
    subscribeFocusRequest(listener) {
      focusListeners.add(listener);
      return () => focusListeners.delete(listener);
    },
    getFocusRequest: (slot) => focusRequests.get(slot) ?? null,
    setFocusRequest(slot, focus) {
      focusRequests.set(slot, focus);
      for (const listener of focusListeners) listener();
    },
    clearFocusRequest(slot) {
      if (!focusRequests.delete(slot)) return;
      for (const listener of focusListeners) listener();
    },
    getVisibleRange: (slot) => visibleRanges.get(slot) ?? null,
    setVisibleRange(slot, range) {
      if (range === null) visibleRanges.delete(slot);
      else visibleRanges.set(slot, range);
    },
  };
}

export const gridStore = createGridStore();
