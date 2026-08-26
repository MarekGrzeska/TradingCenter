import { useCallback, useEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Button } from "./Button";

/**
 * Everything a modal owes the operator: the dimmed ground, the focus it takes and gives back, and `Escape`. Hand-rolled
 * because no jsdom implements `<dialog>.showModal()`, so the native route is a polyfill written for the tests.
 */

/** Everything inside the panel a Tab can land on. Queried per keystroke rather
 *  than cached: the dialog's contents change while it is open — a button goes
 *  disabled the moment work starts — and a stale list would trap focus on an
 *  element that can no longer take it. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** `question` is the width a sentence and two buttons want. `wide` is for a modal that exists *because* its panel was
 *  too narrow, and takes a fixed height to scroll against. `reading` is several pages of prose, limited by the screen. */
const SIZES = {
  question: "max-h-[85vh] w-full max-w-2xl",
  wide: "h-[85vh] w-full max-w-6xl",
  reading: "h-[94vh] w-full max-w-[110rem]",
} as const;

export function ModalShell({
  title,
  size = "question",
  /** While true, `Escape` and the corner cross do nothing — work is in flight and the
   *  dialog is where its outcome will appear. */
  closeDisabled = false,
  /** A cross in the corner, for a dialog whose footer has nothing that reads as backing
   *  out. A question has `Cancel` and does not need one. */
  showCloseButton = false,
  footer,
  onClose,
  children,
}: {
  title: string;
  size?: keyof typeof SIZES;
  closeDisabled?: boolean;
  showCloseButton?: boolean;
  footer?: ReactNode;
  onClose(): void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Where focus was before this opened, so it can be given back — otherwise closing drops the operator at the top
    // of the document and a keyboard walk through the table starts over.
    const opener = document.activeElement;
    panelRef.current?.focus();
    return () => {
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        // Not while the work is in flight: it carries on whether or not the operator is watching, and a dialog that
        // leaves takes the outcome with it (`terminal-dialogs` spec, "Escape w trakcie pracy").
        if (closeDisabled) return;
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const stops = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (stops.length === 0) return;

      const first = stops[0];
      const last = stops[stops.length - 1];
      const active = document.activeElement;
      // Wrapping by hand is what keeps focus off the page behind the dialog.
      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [closeDisabled, onClose],
  );

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={`flex flex-col overflow-hidden rounded border border-border-strong bg-raised text-sm text-ink outline-none ${SIZES[size]}`}
      >
        <div className="flex items-start justify-between gap-3 px-4 pt-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {showCloseButton && (
            <Button
              tone="muted"
              className="leading-6"
              aria-label="Close"
              disabled={closeDisabled}
              onClick={onClose}
            >
              ✕
            </Button>
          )}
        </div>

        {/* A question scrolls as one thing; the taller sizes hand their own columns the
            scrolling, because two of them scrolling together is what made the panel this
            replaced hard to work in. */}
        <div
          className={`flex min-h-0 flex-1 flex-col px-4 pb-4 pt-3 ${
            size === "question" ? "overflow-auto" : "overflow-hidden"
          }`}
        >
          {children}
        </div>

        {footer && <div className="border-t border-border px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}
