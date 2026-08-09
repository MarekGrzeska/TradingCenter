import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

/**
 * The one way the terminal asks for consent — the wizard, deleting a pair's data,
 * retrying a job. Never asked in place (`terminal-dialogs` spec, "Pytanie o zgodę jest
 * dialogiem, nie interfejsem w miejscu"): a question sitting next to one row reads as
 * being about that row, and position speaks louder than any caption.
 *
 * What the caller does not own: work in flight, the second click, the failure and the
 * keyboard. `onConfirm` is awaited with the dialog still up, and a rejection is named
 * inside it — a message thrown at the view the dialog just left has lost the decision it
 * explains.
 *
 * Focus and `Escape` are hand-rolled because no version of jsdom implements
 * `<dialog>.showModal()` (checked 25, 26 and 30), so the native route would put every
 * one of these behaviours behind a polyfill written for the tests rather than the thing
 * that ships.
 */

/** Everything inside the panel a Tab can land on. Queried per keystroke rather
 *  than cached: the dialog's contents change while it is open — a button goes
 *  disabled the moment work starts — and a stale list would trap focus on an
 *  element that can no longer take it. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ConfirmDialog({
  title,
  confirmLabel,
  busyLabel,
  confirmDisabled = false,
  cancelLabel = "Cancel",
  tone = "normal",
  fallbackError = "the action failed",
  closeOnSuccess = true,
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  confirmLabel: string;
  /** Shown on the confirming action while `onConfirm` is still running. */
  busyLabel: string;
  /** For a question that cannot be answered yet — an estimate still loading, say. */
  confirmDisabled?: boolean;
  /** `null` for a dialog with nothing to back out of (a result being acknowledged). */
  cancelLabel?: string | null;
  tone?: "normal" | "danger";
  fallbackError?: string;
  /** `false` when the work answers with something the view underneath will not show —
   *  a partial refusal, say. The caller then swaps this dialog for one carrying that
   *  result, which the operator only acknowledges (`terminal-dialogs` spec, "Praca
   *  udaje się połowicznie"). Never a way to keep asking the same question twice. */
  closeOnSuccess?: boolean;
  /** Rejecting keeps the dialog open and names the reason; resolving ends the question. */
  onConfirm(): void | Promise<void>;
  onClose(): void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    // Where focus was before this opened, so it can be given back — otherwise
    // closing drops the operator at the top of the document and a keyboard walk
    // through the table starts over.
    const opener = document.activeElement;
    panelRef.current?.focus();
    return () => {
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  const confirm = useCallback(async () => {
    setFailure(null);
    setBusy(true);
    try {
      await onConfirm();
      if (closeOnSuccess) onClose();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : fallbackError);
    } finally {
      setBusy(false);
    }
  }, [onConfirm, onClose, fallbackError, closeOnSuccess]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        // Not while the work is in flight: it carries on whether or not the
        // operator is watching, and a dialog that leaves takes the outcome with
        // it (`terminal-dialogs` spec, "Escape w trakcie pracy").
        if (busy) return;
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
    [busy, onClose],
  );

  const confirmClass =
    tone === "danger"
      ? "rounded border border-down px-3 py-1 text-down hover:bg-panel disabled:opacity-40"
      : "rounded border border-accent px-3 py-1 text-ink hover:bg-panel disabled:opacity-40";

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded border border-border bg-panel-strong p-4 text-sm text-ink outline-none"
      >
        <h2 className="text-base font-semibold text-ink">{title}</h2>

        {children}

        {failure && <p className="mt-3 text-critical">{failure}</p>}

        <div className="mt-4 flex justify-end gap-2">
          {cancelLabel !== null && (
            <button
              type="button"
              disabled={busy}
              onClick={onClose}
              className="rounded border border-border px-3 py-1 text-ink-muted hover:text-ink disabled:opacity-40"
            >
              {cancelLabel}
            </button>
          )}
          <button
            type="button"
            disabled={busy || confirmDisabled}
            onClick={confirm}
            className={confirmClass}
          >
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
