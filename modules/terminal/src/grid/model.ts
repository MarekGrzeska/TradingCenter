import {
  RESOLUTIONS,
  newIndicatorSelectionKey,
  type IndicatorSelection,
  type Resolution,
} from "../data/types";
import { isIndicatorColorToken } from "../chart/theme";

/**
 * Six slots exist at all times, with fixed identities; the layout only decides
 * how many of them are visible. That is what lets 3x2 → 2x2 → 3x2 come back
 * with the last two slots still configured (terminal-grid spec, "Przejście na
 * mniejszy układ"), and it keeps React keyed on a stable slot id so changing
 * the layout never remounts a chart onto different data.
 */
export const LAYOUTS = {
  "1x1": { cols: 1, rows: 1 },
  "2x1": { cols: 2, rows: 1 },
  "2x2": { cols: 2, rows: 2 },
  "3x2": { cols: 3, rows: 2 },
} as const;

export type LayoutId = keyof typeof LAYOUTS;

export const LAYOUT_IDS = Object.keys(LAYOUTS) as LayoutId[];

export const SLOT_COUNT = 6;

export const SLOT_IDS = ["s1", "s2", "s3", "s4", "s5", "s6"] as const;

export type SlotId = (typeof SLOT_IDS)[number];

export interface SlotConfig {
  /** null means "no instrument chosen yet" — the slot invites a choice rather
   *  than rendering an empty chart. */
  symbol: string | null;
  resolution: Resolution;
  /** The indicators chosen for this slot, the same way it remembers its
   *  instrument and interval (terminal-grid spec, "Slot pamięta własny zestaw
   *  wskaźników"). An entry whose `id` the catalogue no longer offers is
   *  `Chart`'s problem to notice and skip, not this shape's to validate — this
   *  file only checks that a saved value has the shape a selection ever had. */
  indicators: IndicatorSelection[];
}

export interface GridConfig {
  layout: LayoutId;
  activeSlot: SlotId;
  slots: Record<SlotId, SlotConfig>;
}

export function visibleSlotCount(layout: LayoutId): number {
  const { cols, rows } = LAYOUTS[layout];
  return cols * rows;
}

export function visibleSlotIds(layout: LayoutId): SlotId[] {
  return SLOT_IDS.slice(0, visibleSlotCount(layout));
}

export function defaultGridConfig(): GridConfig {
  return {
    layout: "2x2",
    activeSlot: "s1",
    slots: {
      s1: { symbol: "US100", resolution: "MINUTE_5", indicators: [] },
      s2: { symbol: "GOLD", resolution: "MINUTE_5", indicators: [] },
      s3: { symbol: "BTCUSD", resolution: "HOUR", indicators: [] },
      s4: { symbol: "EURUSD", resolution: "MINUTE_15", indicators: [] },
      s5: { symbol: null, resolution: "MINUTE_5", indicators: [] },
      s6: { symbol: null, resolution: "MINUTE_5", indicators: [] },
    },
  };
}

const RESOLUTION_SET = new Set<string>(RESOLUTIONS);

/**
 * `key` and `colour` are both optional on the way in: a slot saved before an indicator
 * could be chosen twice, or given a colour, carries neither, and rejecting it would cost
 * the operator every indicator in every slot for two fields with obvious defaults
 * (terminal-grid spec, "Slot zapisany przed instancjami i kolorami"). A colour naming a
 * token this palette does not offer is read as no colour, for the same reason.
 */
function readIndicatorSelection(value: unknown): IndicatorSelection | null {
  if (typeof value !== "object" || value === null) return null;
  const selection = value as Record<string, unknown>;
  if (typeof selection.id !== "string") return null;
  if (typeof selection.params !== "object" || selection.params === null) return null;
  const params = selection.params as Record<string, unknown>;
  if (!Object.values(params).every((v) => typeof v === "number")) return null;
  return {
    key: typeof selection.key === "string" ? selection.key : newIndicatorSelectionKey(),
    id: selection.id,
    params: params as Record<string, number>,
    color: isIndicatorColorToken(selection.color) ? selection.color : null,
  };
}

function readSlotConfig(value: unknown): SlotConfig | null {
  if (typeof value !== "object" || value === null) return null;
  const slot = value as Record<string, unknown>;
  if (!(slot.symbol === null || typeof slot.symbol === "string")) return null;
  if (typeof slot.resolution !== "string" || !RESOLUTION_SET.has(slot.resolution)) return null;
  if (!Array.isArray(slot.indicators)) return null;

  const indicators: IndicatorSelection[] = [];
  for (const raw of slot.indicators) {
    const selection = readIndicatorSelection(raw);
    if (selection === null) return null;
    indicators.push(selection);
  }
  return { symbol: slot.symbol, resolution: slot.resolution as Resolution, indicators };
}

/**
 * Hand-written guard rather than a schema library — one shape, one place, no
 * dependency (design.md). Anything that does not pass is discarded whole: a
 * corrupt or older saved config must start the terminal at defaults, never
 * refuse to start (terminal-grid spec, "Zapisany stan jest nieczytelny").
 */
export function parseGridConfig(value: unknown): GridConfig | null {
  if (typeof value !== "object" || value === null) return null;
  const raw = value as Record<string, unknown>;

  if (typeof raw.layout !== "string" || !(raw.layout in LAYOUTS)) return null;
  if (typeof raw.activeSlot !== "string" || !SLOT_IDS.includes(raw.activeSlot as SlotId)) {
    return null;
  }
  if (typeof raw.slots !== "object" || raw.slots === null) return null;

  const rawSlots = raw.slots as Record<string, unknown>;
  const slots = {} as Record<SlotId, SlotConfig>;
  for (const id of SLOT_IDS) {
    const slot = readSlotConfig(rawSlots[id]);
    if (slot === null) return null;
    slots[id] = slot;
  }

  return {
    layout: raw.layout as LayoutId,
    activeSlot: raw.activeSlot as SlotId,
    slots,
  };
}
