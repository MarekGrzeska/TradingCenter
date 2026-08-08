import type { ConnectionState, Resolution, StreamEvent } from "./types";

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

/** Where one pair's stream lives. */
export type UrlFor = (symbol: string, resolution: Resolution) => string;

/** One received frame, in the terminal's vocabulary. Returning a list rather
 *  than one event lets a single frame mean several things — a snapshot carrying
 *  both a settled series and a forming bar — and returning an empty list is how
 *  an unrecognised frame is ignored rather than fatal. */
export type Translate = (raw: string) => StreamEvent[];

type Sink = (event: StreamEvent) => void;

interface HubEntry {
  symbol: string;
  resolution: Resolution;
  sinks: Set<Sink>;
  socket: SocketLike | null;
  state: ConnectionState;
  reconnectAttempt: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  everConnected: boolean;
  torndown: boolean;
}

// min(30s, 2^attempt * 500ms), with ±20% jitter so many slots reconnecting at
// once don't all hit the source in the same instant.
function backoffMs(attempt: number, random: () => number): number {
  const base = Math.min(30_000, 2 ** attempt * 500);
  return Math.round(base * (0.8 + random() * 0.4));
}

const REFUSAL_CLOSE_CODE = 1008; // "refused before accepting" — see the archive's README

/**
 * Ref-counted per (symbol, resolution) WebSocket: the first subscriber opens
 * the connection, later subscribers to the same pair share it, and the last one
 * leaving closes it — terminal-market-data spec, "Jedno połączenie obsługuje
 * wielu odbiorców tej samej pary". Reconnects on drop with growing backoff.
 *
 * **No gap-filling.** There used to be one here: on reconnect the hub fetched
 * recent bars and worked out how far back the outage reached, because the
 * stream it read carried nothing but changes. The archive's subscription opens
 * with a snapshot, and reconnecting therefore delivers the missed bars as a
 * matter of course — the gap closes because the protocol has no gap, not
 * because the browser went looking for one (design.md, "Archiwum jest dla
 * terminala jedynym źródłem świec i strumienia").
 *
 * The protocol itself is not this class's business: `urlFor` says where a pair
 * lives and `translate` says what a frame means, both supplied by whoever is
 * being read.
 */
export class SocketHub {
  private readonly entries = new Map<string, HubEntry>();
  private readonly urlFor: UrlFor;
  private readonly translate: Translate;
  private readonly createSocket: SocketFactory;
  private readonly random: () => number;

  constructor(
    urlFor: UrlFor,
    translate: Translate,
    createSocket: SocketFactory = (url) => new WebSocket(url) as unknown as SocketLike,
    random: () => number = Math.random,
  ) {
    this.urlFor = urlFor;
    this.translate = translate;
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
        everConnected: false,
        torndown: false,
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
   *  reconnecting connection — what a 3x2 grid is measured against. */
  activeConnectionCount(): number {
    return this.entries.size;
  }

  private connect(key: string, entry: HubEntry): void {
    entry.state = entry.everConnected ? "reconnecting" : "connecting";
    this.broadcast(entry, { kind: "status", state: entry.state });

    const socket = this.createSocket(this.urlFor(entry.symbol, entry.resolution));
    entry.socket = socket;

    socket.onopen = () => {
      entry.everConnected = true;
      entry.reconnectAttempt = 0;
      entry.state = "connected";
      this.broadcast(entry, { kind: "status", state: "connected" });
      // Nothing else to do on a reconnect: the snapshot is on its way.
    };

    socket.onmessage = (event) => {
      for (const translated of this.translate(event.data)) {
        this.broadcast(entry, translated);
      }
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
    entry.socket?.close();
    this.entries.delete(key);
  }

  private broadcast(entry: HubEntry, event: StreamEvent): void {
    for (const sink of entry.sinks) {
      sink(event);
    }
  }
}
