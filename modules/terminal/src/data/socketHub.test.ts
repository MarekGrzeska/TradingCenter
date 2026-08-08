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

/**
 * A close with no code to read.
 *
 * The archive refuses a pair nobody collects before the handshake, and a
 * browser cannot see the status of a handshake that was rejected — so the page
 * gets a connection that failed, indistinguishable from an archive that is
 * down. Caught in a real browser, where three of four grid slots sat on
 * "RECONNECTING" forever instead of saying nobody was collecting those pairs.
 */
describe("SocketHub asking why a socket would not open", () => {
  let sockets: FakeSocket[];
  let asked: Array<[string, string]>;

  function hubThatDiagnoses(answer: () => Promise<string | null>): SocketHub {
    return new SocketHub(
      (symbol, resolution) => `ws://localhost/ws?symbol=${symbol}&resolution=${resolution}`,
      translate,
      (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      () => 0.5,
      (symbol, resolution) => {
        asked.push([symbol, resolution]);
        return answer();
      },
    );
  }

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    asked = [];
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stops retrying and says why, when the answer is a reason", async () => {
    const hub = hubThatDiagnoses(async () => "US100 MINUTE_5 is not being archived");
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));

    sockets[0].drop();
    await vi.advanceTimersByTimeAsync(0);

    expect(asked).toEqual([["US100", "MINUTE_5"]]);
    expect(events).toContainEqual({
      kind: "error",
      message: "US100 MINUTE_5 is not being archived",
    });
    expect(events.at(-1)).toEqual({ kind: "status", state: "closed" });

    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(1); // never tried again
  });

  it("goes on retrying when there is no reason to stop", async () => {
    const hub = hubThatDiagnoses(async () => null);
    hub.subscribe("US100", "MINUTE_5", () => {});

    sockets[0].drop();
    await vi.advanceTimersByTimeAsync(1000);

    expect(sockets).toHaveLength(2);
  });

  // The archive not answering is the case retrying exists for, so a failed
  // diagnosis must not be read as "no reason found, therefore stop".
  it("goes on retrying when the question itself fails", async () => {
    const hub = hubThatDiagnoses(async () => {
      throw new Error("the candle archive is not reachable");
    });
    hub.subscribe("US100", "MINUTE_5", () => {});

    sockets[0].drop();
    await vi.advanceTimersByTimeAsync(1000);

    expect(sockets).toHaveLength(2);
  });

  it("asks once per run of failures, not once per attempt", async () => {
    const hub = hubThatDiagnoses(async () => null);
    hub.subscribe("US100", "MINUTE_5", () => {});

    for (let i = 0; i < 4; i++) {
      sockets.at(-1)!.drop();
      await vi.advanceTimersByTimeAsync(30_000);
    }

    expect(sockets.length).toBeGreaterThan(4); // it kept reconnecting
    expect(asked).toHaveLength(1); // and asked once, not five times
  });

  it("asks again after a connection that worked, since the answer can have changed", async () => {
    const hub = hubThatDiagnoses(async () => null);
    hub.subscribe("US100", "MINUTE_5", () => {});

    sockets[0].drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(asked).toHaveLength(1);

    sockets[1].open(); // a pair added in the Archive tab meanwhile
    sockets[1].drop();
    await vi.advanceTimersByTimeAsync(1000);

    expect(asked).toHaveLength(2);
  });

  it("says nothing to a subscriber that has already left", async () => {
    let release: (reason: string | null) => void = () => {};
    const hub = hubThatDiagnoses(() => new Promise((resolve) => (release = resolve)));
    const events: StreamEvent[] = [];
    const unsub = hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));

    sockets[0].drop();
    unsub(); // the slot is closed while the question is still in flight
    release("US100 MINUTE_5 is not being archived");
    await vi.advanceTimersByTimeAsync(0);

    expect(events).not.toContainEqual(
      expect.objectContaining({ kind: "error" }),
    );
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(1);
  });
});
