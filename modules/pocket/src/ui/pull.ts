/** Pull-to-refresh, as arithmetic. The gesture is the mobile idiom for "read it again"; a button in a
 *  corner is the desktop one, and this screen has no corners a thumb reaches. */

/** How far the list has to travel before letting go re-reads. Roughly a thumb's comfortable drag —
 *  short enough to do one-handed, long enough that a flick past the top is not a request. */
export const PULL_THRESHOLD = 64;

/** What the list actually moves when the thumb has travelled `dy` past the top.
 *
 *  Damped and capped: a one-to-one follow feels like a bug at the bottom of the drag, and an
 *  uncapped one lets the whole screen be dragged off. A pull upwards moves nothing at all — that is
 *  a scroll that has not started yet, not a refusal to refresh. */
export function pullOffset(dy: number): number {
  if (dy <= 0) return 0;
  return Math.min(PULL_THRESHOLD * 1.5, dy * 0.5);
}

/** Whether letting go here asks for a read. */
export function shouldRefresh(offset: number): boolean {
  return offset >= PULL_THRESHOLD;
}
