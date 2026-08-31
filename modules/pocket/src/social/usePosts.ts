import { useCallback, useEffect, useState } from "react";
import type { ArchiveState, Post, SocialApi } from "./api";

/** How often the screen re-reads. The archive collects every five minutes, so a phone asking more
 *  often is redrawing the same posts on its own battery.
 *
 *  **It is not a guarantee.** Every mobile browser throttles a background tab and Safari suspends
 *  one outright, which is why the read on `visibilitychange` is the one that matters — and why a
 *  hidden screen does not poll at all: a phone in a pocket has nobody reading the answer. */
export const POLL_MS = 120_000;

export type PostsStatus = "loading" | "ready" | "error";

export interface PostsState {
  posts: Post[];
  archive: ArchiveState | null;
  status: PostsStatus;
  /** The last failure, kept beside the posts rather than instead of them: a failed poll must not
   *  clear a screen somebody is reading. */
  error: string | null;
  lastReadAt: Date | null;
  refreshing: boolean;
  now: Date;
  refresh: () => void;
}

const TICK_MS = 30_000;

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The archive could not be read.";
}

export function usePosts(api: SocialApi, pollMs: number = POLL_MS): PostsState {
  const [posts, setPosts] = useState<Post[]>([]);
  const [archive, setArchive] = useState<ArchiveState | null>(null);
  const [status, setStatus] = useState<PostsStatus>("loading");
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
        // Both in one wait: the posts and what the archive is doing are read together, or an empty
        // list is on screen for a moment before the line explaining it arrives.
        const [nextPosts, nextArchive] = await Promise.all([
          api.recentPosts(controller.signal),
          api.state(controller.signal),
        ]);
        if (cancelled) return;
        setPosts(nextPosts);
        setArchive(nextArchive);
        setStatus("ready");
        setError(null);
        const answered = new Date();
        setLastReadAt(answered);
        setNow(answered);
      } catch (cause) {
        if (cancelled || controller.signal.aborted) return;
        setError(messageOf(cause));
        // Only the first read has nothing to fall back on; `lastReadAt` deliberately does not move,
        // so the header keeps saying how old what is on screen actually is.
        if (initial) setStatus("error");
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    };

    void load(true);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(false);
    }, pollMs);

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

  return { posts, archive, status, error, lastReadAt, refreshing, now, refresh };
}
