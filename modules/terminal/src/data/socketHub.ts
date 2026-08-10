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
 * Where one pair's stream lives — asked afresh for every attempt, retries included,
 * because the archive hands out a one-time ticket for the handshake (a browser cannot
 * put a header on one) and a spent ticket is no ticket at all.
 *
 * Rejecting is meaningful: a `MarketDataError` of kind `unauthenticated` stops the
 * retrying, any other rejection resumes it.
 */
export type UrlFor = (symbol: string, resolution: Resolution) => Promise<string>;

/** One received frame, in the terminal's vocabulary. Returning a list rather
 *  than one event lets a single frame mean several things — a snapshot carrying
 *  both a settled series and a forming bar — and returning an empty list is how
 *  an unrecognised frame is ignored rather than fatal. */
export type Translate = (raw: string) => StreamEvent[];

/**
 * Why a connection that failed will keep failing, or `null` when the failure looks
 * transient.
 *
 * A browser cannot read the status of a rejected WebSocket handshake, so a source
 * refusing with `403` is indistinguishable from one that is down — and "the archive is
 * down" and "nobody chose to collect this pair" ask different things of whoever is
 * looking at the chart. Whoever supplies the socket supplies this second question too.
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
 * Ref-counted per (symbol, resolution) WebSocket: the first subscriber opens the
 * connection, later ones share it, the last one closes it (terminal-market-data spec,
 * "Jedno połączenie obsługuje wielu odbiorców tej samej pary"). Reconnects on drop with
 * growing backoff.
 *
 * No gap-filling, deliberately: the archive's subscription opens with a snapshot, so a
 * reconnect delivers the missed bars as a matter of course. The gap closes because the
 * protocol has none, not because the browser went looking for one.
 *
 * The protocol itself is not this class's business — `urlFor` says where a pair lives
 * and `translate` says what a frame means, both supplied by whoever is being read.
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

  /** The attempt itself, which now begins with a wait: the address has to be
   *  asked for before it can be dialled.
   *
   *  Three ways it can end before a socket exists. The entry was torn down while
   *  the address was in flight — drop it, silently, because nobody is listening.
   *  The operator is signed out — stop, and say so, because no number of
   *  attempts will produce an address. Anything else — retry, because a source
   *  that will not answer right now is the case retrying exists for. */
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

      // A close with no code to read may still be a refusal — a handshake the
      // source rejected outright looks exactly like a source that is down. Ask
      // before settling into a retry loop that cannot succeed.
      if (this.diagnose && !entry.diagnosed) {
        entry.diagnosed = true;
        void this.askWhy(key, entry);
        return;
      }
      this.scheduleReconnect(key, entry);
    };
  }

  /** Runs the second question, then either stops or resumes retrying.
   *
   *  A diagnosis that itself fails resolves nothing and must not be treated as
   *  "no reason found" — the source not answering is the case retrying exists
   *  for. **With one exception**: a diagnosis refused because the operator is
   *  signed out has resolved something, and the answer is not "retry". Without
   *  that exception an expired session looks exactly like an unreachable
   *  archive, and the terminal would retry it forever while never saying the
   *  one thing that would fix it.
   *
   *  Either way the entry may have been torn down while the answer was in
   *  flight, so every path checks before touching it. */
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
