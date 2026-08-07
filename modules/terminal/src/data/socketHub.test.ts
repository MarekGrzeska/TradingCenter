import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SocketHub, type SocketLike } from "./socketHub";
import type { Bar, StreamEvent } from "./types";

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

  message(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  drop(code = 1006, reason = ""): void {
    this.onclose?.({ code, reason });
  }
}

function bar(time: number, close: number, forming = false): Bar {
  return { time, open: close, high: close, low: close, close, volume: null, forming };
}

describe("SocketHub", () => {
  let sockets: FakeSocket[];
  let fetchRecent: ReturnType<typeof vi.fn>;
  let hub: SocketHub;

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    fetchRecent = vi.fn().mockResolvedValue([]);
    hub = new SocketHub(
      "ws://localhost/ws",
      fetchRecent,
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
    expect(sockets[0].url).toBe("ws://localhost/ws/stream?symbol=US100&resolution=MINUTE_5");
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

  it("fans a message out to every sink sharing the pair", () => {
    const events: StreamEvent[][] = [[], []];
    hub.subscribe("US100", "MINUTE_5", (e) => events[0].push(e));
    hub.subscribe("US100", "MINUTE_5", (e) => events[1].push(e));
    sockets[0].open();
    sockets[0].message({
      kind: "candle",
      symbol: "US100",
      resolution: "MINUTE_5",
      time: 100,
      open: 1,
      high: 1,
      low: 1,
      close: 1,
      volume: null,
      forming: true,
    });

    for (const stream of events) {
      const barEvents = stream.filter((e) => e.kind === "bar");
      expect(barEvents).toEqual([{ kind: "bar", bar: bar(100, 1, true) }]);
    }
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

  it("backfills the gap from fetchRecent once a reconnect succeeds", async () => {
    const events: StreamEvent[] = [];
    fetchRecent.mockResolvedValue([bar(200, 2), bar(300, 3)]);
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].open();
    sockets[0].drop();
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);

    sockets[1].open();
    await vi.waitFor(() => {
      expect(fetchRecent).toHaveBeenCalledWith("US100", "MINUTE_5", 50);
    });
    await vi.waitFor(() => {
      const bars = events.filter((e) => e.kind === "bar").map((e) => e.bar);
      expect(bars).toEqual([bar(200, 2), bar(300, 3)]);
    });
  });

  it("does not backfill or reconnect after the very first connect", () => {
    hub.subscribe("US100", "MINUTE_5", () => {});
    sockets[0].open();
    expect(fetchRecent).not.toHaveBeenCalled();
  });

  it("treats a refusal close (1008) as terminal, not transient", () => {
    const events: StreamEvent[] = [];
    hub.subscribe("US100", "MINUTE_5", (e) => events.push(e));
    sockets[0].drop(1008, "symbol is required");

    expect(events).toContainEqual({ kind: "error", message: "symbol is required" });
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
