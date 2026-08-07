/**
 * The terminal's own vocabulary — not capital-gateway's wire shapes. An adapter
 * (gatewaySource.ts) is the only place that ever sees a gateway payload; every
 * other module speaks these types. See design.md, "MarketDataSource — jeden
 * interfejs, trzy przyszłe implementacje".
 */

export const RESOLUTIONS = [
  "MINUTE",
  "MINUTE_5",
  "MINUTE_15",
  "MINUTE_30",
  "HOUR",
  "HOUR_4",
  "DAY",
  "WEEK",
] as const;

export type Resolution = (typeof RESOLUTIONS)[number];

/** Seconds in one period, for resolutions where that is even well-defined.
 *  DAY and WEEK are deliberately absent: a daily candle starts at the venue's
 *  session open, not UTC midnight, so only a source may decide that boundary —
 *  see design.md, Risks: "`DAY` i `WEEK` nie mają stałej długości okresu." */
export const FIXED_RESOLUTION_SECONDS: Readonly<Partial<Record<Resolution, number>>> = {
  MINUTE: 60,
  MINUTE_5: 300,
  MINUTE_15: 900,
  MINUTE_30: 1800,
  HOUR: 3600,
  HOUR_4: 14400,
};

export type AssetClass =
  | "SHARES"
  | "INDICES"
  | "CRYPTO"
  | "CURRENCIES"
  | "COMMODITIES"
  | "OTHER";

export interface Instrument {
  symbol: string;
  name: string;
  assetClass: AssetClass;
  tradeable: boolean;
  bid: number | null;
  ask: number | null;
}

export interface InstrumentPage {
  instruments: Instrument[];
  count: number;
  /** True when the catalogue walk was cut short — a partial list must never be
   *  mistaken for a complete one (terminal-instruments spec). */
  truncated: boolean;
}

/** One candle, in the terminal's one time representation: epoch seconds at the
 *  start of the period, matching what lightweight-charts indexes by and what the
 *  WebSocket already sends. REST's ISO `ts` is converted on the way in — see
 *  time.ts — so nothing downstream of the source implementations ever sees an
 *  ISO string. */
export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  /** null means "this source doesn't carry volume here" (e.g. the WebSocket
   *  feed), never zero. */
  volume: number | null;
  /** True while this bar is still being assembled from quotes and can still
   *  change — see terminal-market-data spec, "Świeca w budowie jest oznaczona
   *  jako niepewna". */
  forming: boolean;
}

export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";

export type StreamEvent =
  | { kind: "bar"; bar: Bar }
  | { kind: "quote"; time: number; bid: number; ask: number }
  | { kind: "status"; state: ConnectionState }
  | { kind: "error"; message: string };

export type MarketDataErrorKind =
  | "not-found"
  | "unsupported-resolution"
  | "unreachable"
  | "unknown";

/** What a failed request or a dead subscription tells the UI. Never carries a
 *  credential and never a raw network error — terminal-market-data spec,
 *  "Zapytanie o dane nazywa swoją porażkę". */
export class MarketDataError extends Error {
  readonly kind: MarketDataErrorKind;

  constructor(kind: MarketDataErrorKind, message: string) {
    super(message);
    this.name = "MarketDataError";
    this.kind = kind;
  }
}
