import { useState } from "react";
import { formatAge } from "../ui/age";
import { Pill } from "../ui/Pill";
import type { Post } from "./api";
import { headline, toneFor } from "./impact";
import styles from "./PostCard.module.css";

/** One post, folded by default. Open, it shows the Polish reading where there is one and the original
 *  where there is not — never an empty body, and never a translation the archive does not hold. */
export function PostCard({ post, now }: { post: Post; now: Date }) {
  const [open, setOpen] = useState(false);
  const body = post.translatedContent ?? post.content;

  return (
    <article className={styles.card}>
      <button
        type="button"
        className={styles.header}
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <span className={styles.meta}>
          <span className={styles.when}>{formatAge(post.publishedAt, now)}</span>
          {post.isRepost && <span className={styles.repost}>RT</span>}
          {post.impactScore !== null && (
            <Pill tone={toneFor(post.impactScore)}>{post.impactScore}/10</Pill>
          )}
        </span>
        <span className={styles.headline}>{headline(body)}</span>
      </button>

      {open && (
        <div className={styles.body}>
          {post.topics.length > 0 && (
            <div className={styles.topics}>
              {post.topics.map((topic) => (
                <span key={topic} className={styles.topic}>
                  {topic}
                </span>
              ))}
            </div>
          )}
          <p className={styles.text}>{body}</p>
          {post.url !== null && (
            <a className={styles.link} href={post.url} target="_blank" rel="noopener noreferrer">
              Open at the source
            </a>
          )}
        </div>
      )}
    </article>
  );
}
