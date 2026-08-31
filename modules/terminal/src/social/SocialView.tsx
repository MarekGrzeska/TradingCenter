import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { socialIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { PostCard } from "./PostCard";
import { HIGH_IMPACT, splitByImpact } from "./impact";
import { createSocialApi, type ArchiveState, type PostsPage, type SocialApi } from "./socialApi";

/**
 * What was said in the last day, and what a model made of it. **The question is "did anything happen that moves a
 * market"**, so the scored posts are open and everything else — the unread included — is one fold away.
 *
 * An empty list is three different facts, and the screen says which: a quiet day, an archive that has stopped
 * hearing from its source, and a window before collection started.
 */

/** How often the list is re-asked. The module collects every five minutes, so this is
 *  frequent enough that a new post appears without a reload and rare enough that the
 *  screen is not asking for an answer that cannot have changed. */
const POLL_MS = 60_000;

const WINDOW_HOURS = 24;

const NO_PAGE: PostsPage = { posts: [], windowFrom: new Date(0), windowTo: new Date(0) };
const NO_STATE: ArchiveState = {
  sources: [],
  postsInWindow: 0,
  windowHours: WINDOW_HOURS,
  modelConfigured: true,
};

export function SocialView({ api }: { api?: SocialApi } = {}) {
  const client = useMemo(
    () => api ?? createSocialApi(resolveEndpoints().socialHttp, socialIdentity),
    [api],
  );
  const [restOpen, setRestOpen] = useState(false);

  const page = useRead<PostsPage>({
    key: ["social", "posts", WINDOW_HOURS],
    read: (signal) => client.recentPosts(WINDOW_HOURS, signal),
    initial: NO_PAGE,
    fallbackMessage: "could not read the posts",
    pollMs: POLL_MS,
    // Kept, deliberately: a failed refresh must not take the posts off a screen the
    // operator is reading. The notice says the last read failed; the list stays.
    onFailure: "keep",
  });

  const state = useRead<ArchiveState>({
    key: ["social", "state"],
    read: (signal) => client.state(signal),
    initial: NO_STATE,
    fallbackMessage: "could not read what the archive is doing",
    pollMs: POLL_MS,
  });

  const { high, rest } = useMemo(() => splitByImpact(page.value.posts), [page.value.posts]);
  const stalled = state.value.sources.filter((source) => source.stale);
  const ready = page.status === "ready";

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Social</h1>
        <span className="text-xs text-ink-faint">
          {page.value.posts.length} {page.value.posts.length === 1 ? "post" : "postów"} · ostatnie{" "}
          {WINDOW_HOURS} h · odświeżane co {POLL_MS / 1000} s
        </span>
      </header>

      {page.error !== null && (
        <UnreachableNotice onRetry={page.reload}>{page.error}</UnreachableNotice>
      )}

      {stalled.length > 0 && (
        <p className="text-sm text-warning">
          {stalled.map((source) => (
            <span key={source.source}>
              Archiwum nie zebrało nic z {source.source} od{" "}
              {source.lastSuccessAt?.toLocaleString("pl-PL") ?? "początku zbioru"}
              {source.lastFailureReason !== null && ` — ${source.lastFailureReason}`}.{" "}
            </span>
          ))}
          Pusta lista nie znaczy, że nic nie napisano.
        </p>
      )}

      {!state.value.modelConfigured && state.status === "ready" && (
        <p className="text-sm text-ink-muted">
          Model nie jest skonfigurowany — oceny wpływu i tłumaczenia nie powstają. Posty są zbierane
          dalej.
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {ready && page.value.posts.length === 0 ? (
          <p className="text-sm text-ink-muted">Brak postów z ostatnich {WINDOW_HOURS} h.</p>
        ) : (
          <>
            {ready && high.length === 0 && page.value.posts.length > 0 && (
              <p className="text-sm text-ink-muted">
                Nic o wpływie {HIGH_IMPACT}/10 lub wyższym w tym oknie.
              </p>
            )}
            {high.map((post) => (
              <PostCard key={`${post.source}:${post.externalId}`} post={post} />
            ))}

            {rest.length > 0 && (
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  className="self-start text-xs text-ink-faint underline"
                  aria-expanded={restOpen}
                  onClick={() => setRestOpen((was) => !was)}
                >
                  {restOpen ? "▲" : "▼"} Pozostałe posty ({rest.length})
                </button>
                {restOpen &&
                  rest.map((post) => (
                    <PostCard key={`${post.source}:${post.externalId}`} post={post} />
                  ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
