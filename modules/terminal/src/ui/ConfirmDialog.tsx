import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { ModalShell } from "./ModalShell";
import { Button } from "./Button";

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
 * The ground, the focus trap and `Escape` live in `ModalShell`, which every modal in the
 * terminal is built on. What is left here is the question itself: the two actions, the work
 * between them, and the failure that has to stay beside the decision it explains.
 */
export function ConfirmDialog({
  title,
  confirmLabel,
  busyLabel,
  confirmDisabled = false,
  cancelLabel = "Cancel",
  size = "question",
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
  /** A question is narrow, which is right for a question. `wide` is for the case where the
   *  consent is over something the operator is *composing* rather than reading — a rule
   *  tree, say — and where a narrow panel makes every row wrap and the thing illegible. */
  size?: "question" | "wide";
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
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

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

  const confirmClass =
    tone === "danger"
      ? "rounded border border-critical bg-critical-soft px-3 py-1 text-critical hover:bg-critical hover:text-ink disabled:opacity-40"
      : "rounded border border-primary bg-primary-soft px-3 py-1 text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:opacity-40";

  return (
    <ModalShell title={title} size={size} closeDisabled={busy} onClose={onClose}
      footer={
        <div className="flex flex-col gap-2">
          {failure && <p className="text-critical">{failure}</p>}
          <div className="flex justify-end gap-2">
            {cancelLabel !== null && (
              <Button
                tone="muted"
                size="md"
                disabled={busy}
                onClick={onClose}
              >
                {cancelLabel}
              </Button>
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
      }
    >
      {children}
    </ModalShell>
  );
}
