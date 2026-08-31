/** What the screen opens with and what it folds away — the same threshold the terminal draws, since it
 *  is one archive and an operator switching devices should not be reading two different lists. */

import type { Post } from "./api";

export const HIGH_IMPACT = 6;

export interface Split {
  high: Post[];
  /** Lower-scored posts *and* every post no model has read: unread is not unimportant, so it is
   *  folded away rather than promoted or dropped. */
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

export type ImpactTone = "ok" | "warn" | "muted";

/** The pill a score is shown in. `null` has no pill at all — a dash or a grey zero would both read
 *  as a judgement, and there is none. */
export function toneFor(score: number): ImpactTone {
  if (score >= 7) return "warn";
  if (score >= 4) return "ok";
  return "muted";
}

/** The opening of a post, for a folded card. Shorter than the terminal's: a phone line holds less. */
export function headline(text: string, max = 90): string {
  const line = text.split("\n")[0].trim();
  return line.length <= max ? line : `${line.slice(0, max).trimEnd()}…`;
}
