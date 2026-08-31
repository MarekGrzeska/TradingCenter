/**
 * What the screen puts in front of the operator and what it folds away. The question the tab answers is
 * "did anything happen that moves a market", not "what was posted today".
 */

import type { Post } from "./socialApi";

/** At and above this, a post is shown without the operator clicking anything. Six is where the source
 *  application drew it, and it stays until a week of looking says otherwise. */
export const HIGH_IMPACT = 6;

export interface Split {
  /** Scored at or above the threshold — shown open. */
  high: Post[];
  /** Everything else, including every post no model has read: unread is not unimportant, so
   *  it is folded away rather than hidden or promoted. */
  rest: Post[];
}

export function splitByImpact(posts: readonly Post[], threshold = HIGH_IMPACT): Split {
  const high: Post[] = [];
  const rest: Post[] = [];
  for (const post of posts) {
    if (post.impactScore !== null && post.impactScore >= threshold) high.push(post);
    else rest.push(post);
  }
  return { high, rest };
}

export type ImpactBand = "high" | "middling" | "low" | "unread";

/** Which band a score falls in, for the badge. `unread` is its own band and not a low score. */
export function bandOf(score: number | null): ImpactBand {
  if (score === null) return "unread";
  if (score >= 7) return "high";
  if (score >= 4) return "middling";
  return "low";
}

/** The first line of a post, shortened — what the card shows before it is opened. */
export function headline(text: string, max = 120): string {
  const line = text.split("\n")[0].trim();
  return line.length <= max ? line : `${line.slice(0, max).trimEnd()}…`;
}
