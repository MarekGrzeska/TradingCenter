import { MarketDataError, type ConnectionState, type Resolution, type StreamEvent } from "./types";

/** The one failure whose answer is "sign in" rather than "try again". */
function isSignedOut(cause: unknown): cause is MarketDataError {
  return cause instanceof MarketDataError && cause.kind === "unauthenticated";
}

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

/**
 * Asked afresh for every attempt, retries included: the archive hands out a one-time ticket for the handshake
 * and a spent one is no ticket. Rejecting with kind `unauthenticated` stops the retrying, anything else resumes it.
 */
export type UrlFor = (symbol: string, resolution: Resolution) => Promise<string>;

/** One received frame, in the terminal's vocabulary. Returning a list rather
 *  than one event lets a single frame mean several things — a snapshot carrying
 *  both a settled series and a forming bar — and returning an empty list is how
 *  an unrecognised frame is ignored rather than fatal. */
export type Translate = (raw: string) => StreamEvent[];

/**
 * Why a failed connection will keep failing, or `null` when it looks transient. A browser cannot read a rejected
 * handshake's status, so a `403` is indistinguishable from a source that is down — hence a second question.
 */
export type Diagnose = (symbol: string, resolution: Resolution) => Promise<string | null>;

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
  /** Asked once per run of failures, not once per attempt: the answer cannot
   *  change between two retries seconds apart, and asking every time would put
   *  a request on the source for every socket it is already refusing. */
  diagnosed: boolean;
}

// min(30s, 2^attempt * 500ms), with ±20% jitter so many slots reconnecting at
// once don't all hit the source in the same instant.
function backoffMs(attempt: number, random: () => number): number {
  const base = Math.min(30_000, 2 ** attempt * 500);
  return Math.round(base * (0.8 + random() * 0.4));
}

const REFUSAL_CLOSE_CODE = 1008; // "refused before accepting" — see the archive's README

/**
 * Ref-counted per (symbol, resolution) socket, reconnecting with growing backoff (terminal-market-data spec).
 * No gap-filling: the archive's subscription opens with a snapshot, so the protocol has no gap to fill.
 */
export class SocketHub {
  private readonly entries = new Map<string, HubEntry>();
  private readonly urlFor: UrlFor;
  private readonly translate: Translate;
  private readonly createSocket: SocketFactory;
  private readonly random: () => number;
  private readonly diagnose: Diagnose | null;

  constructor(
    urlFor: UrlFor,
    translate: Translate,
    createSocket: SocketFactory = (url) => new WebSocket(url) as unknown as SocketLike,
    random: () => number = Math.random,
    diagnose: Diagnose | null = null,
  ) {
    this.urlFor = urlFor;
    this.translate = translate;
    this.createSocket = createSocket;
    this.random = random;
    this.diagnose = diagnose;
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
        diagnosed: false,
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
    void this.open(key, entry);
  }

  /** The attempt begins with a wait: the address has to be asked for before it can be dialled. Torn down while
   *  it was in flight — drop it; signed out — stop, no attempt will produce an address; anything else — retry. */
  private async open(key: string, entry: HubEntry): Promise<void> {
    let url: string;
    try {
      url = await this.urlFor(entry.symbol, entry.resolution);
    } catch (cause) {
      if (entry.torndown || !this.entries.has(key)) return;
      if (isSignedOut(cause)) {
        this.refuse(entry, cause.message);
        return;
      }
      this.scheduleReconnect(key, entry);
      return;
    }
    if (entry.torndown || !this.entries.has(key)) return;

    const socket = this.createSocket(url);
    entry.socket = socket;

    socket.onopen = () => {
      entry.everConnected = true;
      entry.reconnectAttempt = 0;
      entry.diagnosed = false;
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
        this.refuse(entry, event.reason || "subscription refused");
        return;
      }
      entry.state = "reconnecting";
      this.broadcast(entry, { kind: "status", state: "reconnecting" });

      // A close with no code to read may still be a refusal — a rejected handshake looks exactly like a
      // source that is down. Ask before settling into a retry loop that cannot succeed.
      if (this.diagnose && !entry.diagnosed) {
        entry.diagnosed = true;
        void this.askWhy(key, entry);
        return;
      }
      this.scheduleReconnect(key, entry);
    };
  }

  /** A diagnosis that itself fails resolves nothing and must not read as "no reason found". **One exception**:
   *  refused because the operator is signed out has resolved it, and without that an expired session retries forever. */
  private async askWhy(key: string, entry: HubEntry): Promise<void> {
    let reason: string | null = null;
    try {
      reason = await this.diagnose!(entry.symbol, entry.resolution);
    } catch (cause) {
      if (entry.torndown || !this.entries.has(key)) return;
      if (isSignedOut(cause)) {
        this.refuse(entry, cause.message);
        return;
      }
      reason = null;
    }
    if (entry.torndown || !this.entries.has(key)) return;
    if (reason !== null) {
      this.refuse(entry, reason);
      return;
    }
    this.scheduleReconnect(key, entry);
  }

  /** A failure that retrying cannot fix: say why, and stop. */
  private refuse(entry: HubEntry, message: string): void {
    entry.state = "closed";
    this.broadcast(entry, { kind: "error", message });
    this.broadcast(entry, { kind: "status", state: "closed" });
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
