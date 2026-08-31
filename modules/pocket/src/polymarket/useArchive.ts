import { useCallback, useEffect, useState } from "react";
import type { PolymarketApi, TrackedEvent } from "./api";

/** How often the screen re-reads. The archive samples once a minute, so asking more often costs a
 *  phone's battery to redraw the same numbers. */
export const POLL_MS = 60_000;

export type ArchiveStatus = "loading" | "ready" | "error";

export interface ArchiveState {
  events: TrackedEvent[];
  /** Group names the archive knows, including ones nothing is filed under yet. */
  groups: string[];
  status: ArchiveStatus;
  /** The last failure, kept beside the data rather than instead of it: a poll that fails should
   *  say so without blanking prices the operator was reading a second ago. */
  error: string | null;
  /** Moves with each successful read, so ages and staleness are recomputed from one moment rather
   *  than from whenever each row happened to render. */
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
  const [now, setNow] = useState(() => new Date());
  const [attempt, setAttempt] = useState(0);

  const refresh = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const load = async (initial: boolean) => {
      try {
        // Both in one round trip's worth of waiting: the chips come from the groups and the
        // sections from the events, and a screen drawn from two moments flickers a heading.
        const [nextEvents, nextGroups] = await Promise.all([
          api.listEvents(controller.signal),
          api.listGroups(controller.signal),
        ]);
        if (cancelled) return;
        setEvents(nextEvents);
        setGroups(nextGroups.map((group) => group.name));
        setStatus("ready");
        setError(null);
        setNow(new Date());
      } catch (cause) {
        if (cancelled || controller.signal.aborted) return;
        setError(messageOf(cause));
        // Only the first read has nothing to fall back on. A failed poll keeps the last answer
        // on screen and adds a line saying it is the last answer.
        if (initial) setStatus("error");
      }
    };

    void load(true);
    const interval = window.setInterval(() => void load(false), pollMs);

    // A phone spends most of its time with the screen off, and coming back to a minute-old price
    // that says "just now" is the one lie this screen must not tell.
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

  return { events, groups, status, error, now, refresh };
}
