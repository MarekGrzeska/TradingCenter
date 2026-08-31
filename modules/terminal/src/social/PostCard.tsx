import { useState } from "react";
import { formatInstant } from "../ui/formatTime";
import { bandOf, headline } from "./impact";
import type { Post } from "./socialApi";

/**
 * One post, folded. The body shows the Polish reading where a model produced one and the original where it did
 * not — never an empty panel, and never a translation the archive does not hold.
 */

const BAND_CLASS: Record<string, string> = {
  high: "bg-critical-soft text-critical",
  middling: "bg-warning-soft text-warning",
  low: "bg-raised text-ink-muted",
};

function ScoreBadge({ score }: { score: number | null }) {
  // No badge at all for a post no model has read: a zero, a dash or a grey "?" would all read
  // as a judgement, and there is none.
  if (score === null) return null;
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${BAND_CLASS[bandOf(score)]}`}
      title={`market impact ${score}/10`}
    >
      {score}/10
    </span>
  );
}

export function PostCard({ post }: { post: Post }) {
  const [open, setOpen] = useState(false);
  const body = post.translatedContent ?? post.content;

  return (
    <article className="rounded border border-border bg-panel">
      <button
        type="button"
        className="flex w-full items-start gap-3 px-3 py-2 text-left"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="flex shrink-0 items-center gap-2 pt-0.5">
          <span className="text-xs tabular-nums text-ink-faint">
            {formatInstant(Math.floor(post.publishedAt.getTime() / 1000))}
          </span>
          {post.isRepost && (
            <span className="rounded bg-raised px-1 text-[11px] text-ink-muted">RT</span>
          )}
          <ScoreBadge score={post.impactScore} />
        </span>
        <span className="min-w-0 flex-1 text-sm text-ink">{headline(body)}</span>
        <span className="shrink-0 text-xs text-ink-faint" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-3 py-2">
          {post.topics.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {post.topics.map((topic) => (
                <span
                  key={topic}
                  className="rounded bg-raised px-1.5 py-0.5 text-[11px] text-ink-muted"
                >
                  {topic}
                </span>
              ))}
            </div>
          )}
          <p className="whitespace-pre-wrap text-sm text-ink">{body}</p>
          <div className="mt-2 flex items-center gap-3 text-xs text-ink-faint">
            {post.translatedContent !== null && <span>przetłumaczone</span>}
            {post.analysedModel !== null && <span>ocena: {post.analysedModel}</span>}
            {post.url !== null && (
              <a
                className="text-accent underline"
                href={post.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                otwórz u źródła
              </a>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
