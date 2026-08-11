import { useSyncExternalStore } from "react";

import { toastStore, type Toast } from "./toastStore";

/**
 * Mounted once, in `Shell`. Everything that wants to say something calls `showToast`;
 * nothing else renders one (`toastsComeFromOnePlace.test.ts`).
 *
 * Deliberately not a dialog: it takes no focus, traps none, and blocks nothing. A toast
 * that stole focus from a chart the operator is reading would be worse than the silence
 * it replaced — and `ConfirmDialog` stays the only component in the terminal announcing
 * itself as one (`terminal-dialogs` spec, "Wszystkie dialogi wychodzą z jednego
 * miejsca"). That guard reads source text rather than rendered output, so naming the
 * attribute here — even to say this file does not use it — is what trips it.
 */
export function Toaster() {
  const toasts = useSyncExternalStore(toastStore.subscribe, toastStore.getSnapshot);
  if (toasts.length === 0) return null;

  return (
    <div
      // `polite`, not `assertive`: none of this interrupts what the operator is doing,
      // and an archive refusing one indicator is not worth cutting a screen reader off
      // mid-sentence for.
      aria-live="polite"
      aria-label="Notifications"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
    >
      {toasts.map((toast) => (
        <ToastLine key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

function ToastLine({ toast }: { toast: Toast }) {
  const error = toast.severity === "error";
  return (
    <div
      role={error ? "alert" : "status"}
      className={`pointer-events-auto rounded border bg-panel p-2 shadow-lg ${
        error ? "border-critical/50" : "border-border"
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className={`text-xs font-medium ${error ? "text-critical" : "text-ink"}`}>
            {toast.title}
          </p>
          {toast.detail && (
            // `wrap-break-word`: the detail is a server message and can be one long
            // unbroken string, which would otherwise push the panel off screen.
            <p className="mt-0.5 text-[11px] wrap-break-word text-ink-muted">{toast.detail}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => toastStore.dismiss(toast.id)}
          aria-label={`Dismiss: ${toast.title}`}
          className="shrink-0 rounded px-1 text-xs text-ink-muted hover:bg-panel-strong hover:text-ink"
        >
          ×
        </button>
      </div>
    </div>
  );
}
