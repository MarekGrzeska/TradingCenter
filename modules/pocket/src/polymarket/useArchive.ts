import { useCallback, useEffect, useState } from "react";
import type { PolymarketApi, TrackedEvent } from "./api";

/** How often the screen re-reads. The archive samples once a minute, so asking more often costs a
 *  phone's battery to redraw the same numbers.
 *
 *  **It is not a guarantee.** A backgrounded tab is throttled by every mobile browser and suspended
 *  outright by Safari, which is why the read on `visibilitychange` below is the one that matters and
 *  why the screen says out loud how old its answer is. */
export const POLL_MS = 60_000;

/** How often the displayed ages move. Independent of the poll: "4 min ago" has to keep counting while
 *  the archive is quiet, or a frozen label reads as a fresh price. */
const TICK_MS = 30_000;

export type ArchiveStatus = "loading" | "ready" | "error";

export interface ArchiveState {
  events: TrackedEvent[];
  /** Group names the archive knows, including ones nothing is filed under yet. */
  groups: string[];
  status: ArchiveStatus;
  /** The last failure, kept beside the data rather than instead of it: a poll that fails should say
   *  so without blanking prices the operator was reading a second ago. */
  error: string | null;
  /** When the archive last answered. What every age on the screen is measured from, and what the
   *  header says out loud — a polled screen that cannot be trusted to have polled is worse than one
   *  that admits when it last did. */
  lastReadAt: Date | null;
  /** A read is in flight. The pull gesture and the header both show it. */
  refreshing: boolean;
  /** The clock, ticking on its own so ages advance between reads. */
  now: Date;
  refresh: () => void;
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The archive could not be read.";
}

export function useArchive(api: PolymarketApi, pollMs: number = POLL_MS): ArchiveState {
  const [events, setEvents] = useState<TrackedEvent[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [status, setStatus] = useState<ArchiveStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastReadAt, setLastReadAt] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [attempt, setAttempt] = useState(0);

  const refresh = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const ticking = window.setInterval(() => setNow(new Date()), TICK_MS);
    return () => window.clearInterval(ticking);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const load = async (initial: boolean) => {
      setRefreshing(true);
      try {
        // Both in one round trip's worth of waiting: the chips come from the groups and the sections
        // from the events, and a screen drawn from two moments flickers a heading.
        const [nextEvents, nextGroups] = await Promise.all([
          api.listEvents(controller.signal),
          api.listGroups(controller.signal),
        ]);
        if (cancelled) return;
        setEvents(nextEvents);
        setGroups(nextGroups.map((group) => group.name));
        setStatus("ready");
        setError(null);
        const answered = new Date();
        setLastReadAt(answered);
        setNow(answered);
      } catch (cause) {
        if (cancelled || controller.signal.aborted) return;
        setError(messageOf(cause));
        // Only the first read has nothing to fall back on. A failed poll keeps the last answer on
        // screen — and `lastReadAt` deliberately does not move, so the header says how old it is.
        if (initial) setStatus("error");
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    };

    void load(true);
    const interval = window.setInterval(() => void load(false), pollMs);

    // A phone spends most of its time with the screen off, and every mobile browser throttles or
    // suspends a background tab: this, not the interval, is what makes the screen current again.
    const onVisibility = () => {
      if (document.visibilityState === "visible") void load(false);
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [api, pollMs, attempt]);

  return { events, groups, status, error, lastReadAt, refreshing, now, refresh };
}
