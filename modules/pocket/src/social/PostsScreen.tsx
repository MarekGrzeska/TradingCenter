import { useMemo, useRef, useState } from "react";
import { formatAge } from "../ui/age";
import { PULL_THRESHOLD } from "../ui/pull";
import { usePullToRefresh } from "../ui/usePullToRefresh";
import type { SocialApi } from "./api";
import { HIGH_IMPACT, splitByImpact } from "./impact";
import { PostCard } from "./PostCard";
import { usePosts } from "./usePosts";
import styles from "./PostsScreen.module.css";

/**
 * What was said in the last day, on a phone. The scored posts are the screen; everything else — the
 * unread included — is behind one tap, because a thumb-length list of forty is not read, it is scrolled past.
 */
export function PostsScreen({ api }: { api: SocialApi }) {
  const { posts, archive, status, error, lastReadAt, refreshing, now, refresh } = usePosts(api);
  const [restOpen, setRestOpen] = useState(false);

  const scroller = useRef<HTMLDivElement>(null);
  const pull = usePullToRefresh(scroller, refresh);

  const { high, rest } = useMemo(() => splitByImpact(posts), [posts]);
  const stalled = archive?.sources.filter((source) => source.stale) ?? [];

  const freshness = refreshing
    ? "reading…"
    : lastReadAt === null
      ? "not read yet"
      : `updated ${formatAge(lastReadAt, now)}`;

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <h1 className={styles.heading}>Posts</h1>
        {/* The freshness line is the refresh control, as on the markets screen: a separate button
            would duplicate the poll and the pull gesture without saying anything they do not. */}
        <button type="button" className={styles.freshness} onClick={refresh}>
          {freshness} · last 24 h
        </button>
      </header>

      <div className={styles.scroller} ref={scroller}>
        <div
          className={[styles.pull, pull >= PULL_THRESHOLD ? styles.pullReady : styles.pullPending]
            .filter(Boolean)
            .join(" ")}
          style={{ height: pull }}
        >
          {pull > 0 && (pull >= PULL_THRESHOLD ? "Release to refresh" : "Pull to refresh")}
        </div>

        {error !== null && <p className={styles.error}>{error}</p>}

        {stalled.map((source) => (
          <p key={source.source} className={styles.warning}>
            No posts collected from {source.source} since{" "}
            {source.lastSuccessAt === null ? "collection started" : formatAge(source.lastSuccessAt, now)}
            {source.lastFailureReason !== null && ` — ${source.lastFailureReason}`}. An empty list is
            not a quiet day.
          </p>
        ))}

        {archive !== null && !archive.modelConfigured && (
          <p className={styles.note}>
            No model is configured — impact scores and translations are not being produced. Posts are
            still collected.
          </p>
        )}

        {status === "loading" && <p className={styles.note}>Reading the archive…</p>}

        {status !== "loading" && posts.length === 0 && (
          <p className={styles.note}>Nothing posted in the last 24 h.</p>
        )}

        {posts.length > 0 && high.length === 0 && (
          <p className={styles.note}>Nothing scored {HIGH_IMPACT}/10 or higher in this window.</p>
        )}

        <div className={styles.list}>
          {high.map((post) => (
            <PostCard key={`${post.source}:${post.externalId}`} post={post} now={now} />
          ))}

          {rest.length > 0 && (
            <>
              <button
                type="button"
                className={styles.more}
                aria-expanded={restOpen}
                onClick={() => setRestOpen((was) => !was)}
              >
                {restOpen ? "Hide" : "Show"} the other {rest.length}
              </button>
              {restOpen &&
                rest.map((post) => (
                  <PostCard key={`${post.source}:${post.externalId}`} post={post} now={now} />
                ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
