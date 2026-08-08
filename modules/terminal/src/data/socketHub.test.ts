import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SocketHub, type SocketLike } from "./socketHub";
import type { StreamEvent } from "./types";

class FakeSocket implements SocketLike {
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.();
  }

  message(payload: string): void {
    this.onmessage?.({ data: payload });
  }

  drop(code = 1006, reason = ""): void {
    this.onclose?.({ code, reason });
  }
}

// The hub knows nothing about any protocol — a frame is whatever `translate`
// says it is. These tests use the plainest possible one, so what fails here is
// the ref-counting and the reconnecting rather than someone's wire format.
const translate = (raw: string): StreamEvent[] =>
  raw === "" ? [] : [{ kind: "error", message: raw }];

describe("SocketHub", () => {
  let sockets: FakeSocket[];
  let hub: SocketHub;

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    hub = new SocketHub(
      (symbol, resolution) => `ws://localhost/ws/candles?symbol=${symbol}&resolution=${resolution}`,
      translate,
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      () => 0.5, // fixed jitter midpoint, deterministic backoff
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("opens one socket for the first subscriber, addressed at the pair", () => {
    hub.subscribe("US100", "MINUTE_5", () => {});
    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toBe(
      "ws://localhost/ws/candles?symbol=US100&resolution=MINUTE_5",
    );
  });

  it("shares one socket between subscribers to the same pair", () => {
    hub.subscribe("US100", "MINUTE_5", () => {});
    hub.subscribe("US100", "MINUTE_5", () => {});
    expect(sockets).toHaveLength(1);
    expect(hub.activeConnectionCount()).toBe(1);
  });

  it("opens a separate socket per distinct pair", () => {
    hub.subscribe("US100", "MINUTE_5", () => {});
    hub.subscribe("US100", "MINUTE_15", () => {});
    hub.subscribe("GOLD", "MINUTE_5", () => {});
    expect(sockets).toHaveLength(3);
    expect(hub.activeConnectionCount()).toBe(3);
  });

  it("fans every translated event out to every sink sharing the pair", () => {
    const events: StreamEvent[][] = [[], []];
    hub.subscribe("US100", "MINUTE_5", (e) => events[0].push(e));
    hub.subscribe("US100", "MINUTE_5", (e) => events[1].push(e));
    sockets[0].open();
    sockets[0].message("a frame");

    for (const stream of events) {
      expect(stream).toContainEqual({ kind: "error", message: "a frame" });
    }
  });

  it("drops a frame the translation makes nothing of, instead of passing it on", () => {
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].open();
    const before = events.length;
    sockets[0].message("");
    expect(events).toHaveLength(before);
  });

  it("closes the socket only once the last subscriber leaves", () => {
    const unsubA = hub.subscribe("US100", "MINUTE_5", () => {});
    const unsubB = hub.subscribe("US100", "MINUTE_5", () => {});
    unsubA();
    expect(sockets[0].closed).toBe(false);
    expect(hub.activeConnectionCount()).toBe(1);
    unsubB();
    expect(sockets[0].closed).toBe(true);
    expect(hub.activeConnectionCount()).toBe(0);
  });

  it("delivers the current status immediately to a newly joining sink", () => {
    hub.subscribe("US100", "MINUTE_5", () => {});
    sockets[0].open();

    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    expect(events).toEqual([{ kind: "status", state: "connected" }]);
  });

  it("reconnects on an unexpected drop with growing backoff, and reopens the socket", () => {
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].open();
    sockets[0].drop(1006, "connection reset");

    expect(events.at(-1)).toEqual({ kind: "status", state: "reconnecting" });
    expect(sockets).toHaveLength(1); // not yet reconnected — waiting out the backoff

    vi.advanceTimersByTime(500 * 0.8 + 500 * 0.4 * 0.5); // attempt 0: 2^0*500 * (0.8+0.2)
    expect(sockets).toHaveLength(2);
  });

  // What used to happen here was a backfill: work out how far back the outage
  // reached and fetch it. The archive's subscription opens with a snapshot, so
  // reconnecting delivers the missed bars by itself — the hub reopens the
  // socket and does nothing else (terminal-market-data spec, "Połączenie
  // wraca": the terminal MUST NOT ask for the gap separately).
  it("asks for nothing after a reconnect beyond reopening the socket", () => {
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].open();
    sockets[0].drop();
    vi.advanceTimersByTime(1000);
    sockets[1].open();

    expect(sockets).toHaveLength(2);
    expect(events.at(-1)).toEqual({ kind: "status", state: "connected" });
    // Whatever the reconnected socket sends is simply passed on — a snapshot
    // like any other frame.
    sockets[1].message("the snapshot");
    expect(events.at(-1)).toEqual({ kind: "error", message: "the snapshot" });
  });

  it("treats a refusal close (1008) as terminal, not transient", () => {
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].drop(1008, "US100 MINUTE_5 is not being collected");

    expect(events).toContainEqual({
      kind: "error",
      message: "US100 MINUTE_5 is not being collected",
    });
    expect(events.at(-1)).toEqual({ kind: "status", state: "closed" });

    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1); // no reconnect attempted
  });

  it("stops reconnecting once every subscriber has left before the timer fires", () => {
    const unsub = hub.subscribe("US100", "MINUTE_5", () => {});
    sockets[0].open();
    sockets[0].drop();
    unsub();

    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1); // the dangling reconnect never re-opened a socket
  });
});
