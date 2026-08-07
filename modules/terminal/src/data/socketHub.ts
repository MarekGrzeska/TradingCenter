import type { Bar, ConnectionState, Resolution, StreamEvent } from "./types";

/** The subset of the WebSocket surface the hub touches — injectable so tests
 *  drive a fake transport instead of a real socket. */
export interface SocketLike {
  onopen: (() => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  close(): void;
}

export type SocketFactory = (url: string) => SocketLike;

export type FetchRecent = (
  symbol: string,
  resolution: Resolution,
  count: number,
  signal: AbortSignal,
) => Promise<Bar[]>;

type Sink = (event: StreamEvent) => void;

interface HubEntry {
  symbol: string;
  resolution: Resolution;
  sinks: Set<Sink>;
  socket: SocketLike | null;
  state: ConnectionState;
  reconnectAttempt: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  lastBarTime: number | null;
  everConnected: boolean;
  torndown: boolean;
  backfill: AbortController | null;
}

// min(30s, 2^attempt * 500ms), with ±20% jitter so many slots reconnecting at
// once don't all hit the gateway in the same instant.
function backoffMs(attempt: number, random: () => number): number {
  const base = Math.min(30_000, 2 ** attempt * 500);
  return Math.round(base * (0.8 + random() * 0.4));
}

const REFUSAL_CLOSE_CODE = 1008; // gateway's "refused before accepting" — see its README

// Backfill after a reconnect can't turn the outage's length into a bar count:
// that would need a per-resolution period length, which `DAY` and `WEEK` don't
// have (see types.ts). So the hub asks for a batch, checks whether it reaches
// back past the last bar seen before the drop, and doubles the ask when it
// doesn't — the source itself answers how many bars the gap took.
const BACKFILL_FIRST_BATCH = 50;
const BACKFILL_MAX_BATCH = 400;

/**
 * Ref-counted per (symbol, resolution) WebSocket: the first subscriber opens
 * the connection, later subscribers to the same pair share it, and the last one
 * leaving closes it — terminal-market-data spec, "Jedno połączenie obsługuje
 * wielu odbiorców tej samej pary". Reconnects on drop with growing backoff and
 * backfills the gap from `fetchRecent` once the socket is back.
 */
export class SocketHub {
  private readonly entries = new Map<string, HubEntry>();
  private readonly wsBase: string;
  private readonly fetchRecent: FetchRecent;
  private readonly createSocket: SocketFactory;
  private readonly random: () => number;

  constructor(
    wsBase: string,
    fetchRecent: FetchRecent,
    createSocket: SocketFactory = (url) => new WebSocket(url) as unknown as SocketLike,
    random: () => number = Math.random,
  ) {
    this.wsBase = wsBase;
    this.fetchRecent = fetchRecent;
    this.createSocket = createSocket;
    this.random = random;
  }

  subscribe(symbol: string, resolution: Resolution, sink: Sink): () => void {
    const key = `${symbol}|${resolution}`;
    let entry = this.entries.get(key);
    if (!entry) {
      entry = {
        symbol,
        resolution,
        sinks: new Set(),
        socket: null,
        state: "connecting",
        reconnectAttempt: 0,
        reconnectTimer: null,
        lastBarTime: null,
        everConnected: false,
        torndown: false,
        backfill: null,
      };
      this.entries.set(key, entry);
      this.connect(key, entry);
    }
    entry.sinks.add(sink);
    sink({ kind: "status", state: entry.state });

    return () => {
      const current = this.entries.get(key);
      if (!current) return;
      current.sinks.delete(sink);
      if (current.sinks.size === 0) {
        this.teardown(key, current);
      }
    };
  }

  /** How many distinct (symbol, resolution) pairs currently hold an open or
   *  reconnecting connection — what task 8.3 measures against a 3x2 grid. */
  activeConnectionCount(): number {
    return this.entries.size;
  }

  private connect(key: string, entry: HubEntry): void {
    entry.state = entry.everConnected ? "reconnecting" : "connecting";
    this.broadcast(entry, { kind: "status", state: entry.state });

    const url = `${this.wsBase}/stream?symbol=${encodeURIComponent(entry.symbol)}&resolution=${entry.resolution}`;
    const socket = this.createSocket(url);
    entry.socket = socket;

    socket.onopen = () => {
      const wasReconnect = entry.everConnected;
      entry.everConnected = true;
      entry.reconnectAttempt = 0;
      entry.state = "connected";
      this.broadcast(entry, { kind: "status", state: "connected" });
      if (wasReconnect) {
        void this.backfillGap(entry);
      }
    };

    socket.onmessage = (event) => {
      this.handleMessage(entry, event.data);
    };

    socket.onerror = () => {
      // The close that follows carries the actual reason; nothing to act on here.
    };

    socket.onclose = (event) => {
      if (entry.torndown) return;
      if (event.code === REFUSAL_CLOSE_CODE) {
        entry.state = "closed";
        this.broadcast(entry, {
          kind: "error",
          message: event.reason || "subscription refused",
        });
        this.broadcast(entry, { kind: "status", state: "closed" });
        return;
      }
      entry.state = "reconnecting";
      this.broadcast(entry, { kind: "status", state: "reconnecting" });
      this.scheduleReconnect(key, entry);
    };
  }

  private handleMessage(entry: HubEntry, raw: string): void {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }

    switch (message.kind) {
      case "candle": {
        const bar: Bar = {
          time: message.time as number,
          open: message.open as number,
          high: message.high as number,
          low: message.low as number,
          close: message.close as number,
          volume: (message.volume as number | null) ?? null,
          forming: Boolean(message.forming),
        };
        entry.lastBarTime =
          entry.lastBarTime === null ? bar.time : Math.max(entry.lastBarTime, bar.time);
        this.broadcast(entry, { kind: "bar", bar });
        break;
      }
      case "quote": {
        this.broadcast(entry, {
          kind: "quote",
          time: message.time as number,
          bid: message.bid as number,
          ask: message.ask as number,
        });
        break;
      }
      case "status": {
        entry.state = message.state as ConnectionState;
        this.broadcast(entry, { kind: "status", state: entry.state });
        break;
      }
      case "error": {
        this.broadcast(entry, { kind: "error", message: message.message as string });
        break;
      }
    }
  }

  private async backfillGap(entry: HubEntry): Promise<void> {
    // The bar the stream last carried before the drop: everything after it is
    // the gap. Snapshotted now because the live socket keeps moving it while
    // the backfill is in flight.
    const lastBeforeDrop = entry.lastBarTime;
    const controller = new AbortController();
    entry.backfill?.abort();
    entry.backfill = controller;

    try {
      let count = BACKFILL_FIRST_BATCH;
      let bars: Bar[] = [];
      for (;;) {
        bars = await this.fetchRecent(entry.symbol, entry.resolution, count, controller.signal);
        if (entry.torndown || entry.backfill !== controller) return;
        // Covered once the oldest bar of the batch sits at or before the last
        // one seen. A batch shorter than asked for means the source has no
        // more history, so asking again would return the same bars.
        const reachesBack =
          lastBeforeDrop === null || bars.length === 0 || bars[0].time <= lastBeforeDrop;
        if (reachesBack || bars.length < count || count >= BACKFILL_MAX_BATCH) break;
        count = Math.min(count * 2, BACKFILL_MAX_BATCH);
      }
      // Each bar replaces or appends via the consumer's own mergeBar, so
      // re-sending already-known bars is harmless.
      for (const bar of bars) {
        this.broadcast(entry, { kind: "bar", bar });
      }
    } catch {
      // The live socket is already back; a failed or aborted backfill just
      // leaves the gap for the next settled candle to close naturally.
    } finally {
      if (entry.backfill === controller) {
        entry.backfill = null;
      }
    }
  }

  private scheduleReconnect(key: string, entry: HubEntry): void {
    if (entry.sinks.size === 0) return;
    const attempt = entry.reconnectAttempt++;
    const delay = backoffMs(attempt, this.random);
    entry.reconnectTimer = setTimeout(() => {
      if (!this.entries.has(key) || entry.sinks.size === 0) return;
      this.connect(key, entry);
    }, delay);
  }

  private teardown(key: string, entry: HubEntry): void {
    entry.torndown = true;
    if (entry.reconnectTimer !== null) {
      clearTimeout(entry.reconnectTimer);
    }
    // A backfill outlives the socket it was triggered by unless it is cut off
    // here: the last subscriber is gone, so nobody is left to receive its bars.
    entry.backfill?.abort();
    entry.backfill = null;
    entry.socket?.close();
    this.entries.delete(key);
  }

  private broadcast(entry: HubEntry, event: StreamEvent): void {
    for (const sink of entry.sinks) {
      sink(event);
    }
  }
}
