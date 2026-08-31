import { useEffect, useRef, useState, type RefObject } from "react";
import { pullOffset, shouldRefresh } from "./pull";

/**
 * The gesture, wired to one scrolling element. Only from the very top: a pull that begins mid-list is
 * a scroll, and hijacking it is how a list becomes impossible to read.
 *
 * `touchmove` is registered non-passively on purpose — the pull has to be able to call
 * `preventDefault`, or the browser's own overscroll runs underneath it and both move at once.
 */
export function usePullToRefresh(
  scroller: RefObject<HTMLElement | null>,
  onRefresh: () => void,
): number {
  const [offset, setOffset] = useState(0);
  // In a ref, not state: the handlers are registered once and would otherwise close over the first
  // render's values for as long as the screen is open.
  const start = useRef<number | null>(null);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    const element = scroller.current;
    if (element === null) return;

    const onStart = (event: TouchEvent) => {
      start.current = element.scrollTop <= 0 ? (event.touches[0]?.clientY ?? null) : null;
    };

    const onMove = (event: TouchEvent) => {
      if (start.current === null) return;
      const y = event.touches[0]?.clientY;
      if (y === undefined) return;
      const next = pullOffset(y - start.current);
      if (next > 0) {
        // The list is following the thumb now, so the page must not also bounce.
        event.preventDefault();
      }
      setOffset(next);
    };

    const onEnd = () => {
      if (start.current !== null && shouldRefresh(offset)) {
        refresh.current();
      }
      start.current = null;
      setOffset(0);
    };

    element.addEventListener("touchstart", onStart, { passive: true });
    element.addEventListener("touchmove", onMove, { passive: false });
    element.addEventListener("touchend", onEnd);
    element.addEventListener("touchcancel", onEnd);
    return () => {
      element.removeEventListener("touchstart", onStart);
      element.removeEventListener("touchmove", onMove);
      element.removeEventListener("touchend", onEnd);
      element.removeEventListener("touchcancel", onEnd);
    };
  }, [scroller, offset]);

  return offset;
}
