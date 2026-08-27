/** Roughly what `DrawingCard` occupies before its editor is opened — enough for the
 *  description and the two buttons. The card is anchored by its top-left corner, so the
 *  editor is free to grow past this. */
const CARD_WIDTH = 224;
const CARD_HEIGHT = 120;
const GAP = 12;

/**
 * Where the card describing the picked object stands: on the side of the click that has room for it. Always
 * opening right would drop it off the pane for an object near the right edge, the one most often looked at.
 */
export function cardPosition(
  at: { x: number; y: number } | null,
  pane: { width: number; height: number },
): { left: number; top: number } {
  // Picked from the list: nothing on the chart was clicked, so the card sits where it can
  // be found rather than where a pointer happened to be.
  if (at === null) return { left: GAP, top: GAP };
  const left =
    at.x + GAP + CARD_WIDTH <= pane.width ? at.x + GAP : Math.max(GAP, at.x - GAP - CARD_WIDTH);
  const top =
    at.y + GAP + CARD_HEIGHT <= pane.height ? at.y + GAP : Math.max(GAP, at.y - GAP - CARD_HEIGHT);
  return { left, top };
}
