import { useSyncExternalStore } from "react";

import { toastStore, type Toast } from "./toastStore";

/**
 * Mounted once in `Shell`; everything that wants to say something calls `showToast`. Deliberately not a dialog: it takes
 * no focus and blocks nothing — one stealing focus from a chart would be worse than the silence it replaced.
 */
export function Toaster() {
  const toasts = useSyncExternalStore(toastStore.subscribe, toastStore.getSnapshot);
  if (toasts.length === 0) return null;

  return (
    <div
      // `polite`, not `assertive`: none of this interrupts what the operator is doing, and an archive refusing one
      // indicator is not worth cutting a screen reader off mid-sentence for.
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
      // `raised`, not `panel`: this floats over whatever raised it, and a toast the same
      // colour as the pane beneath it looked like part of that pane.
      className={`pointer-events-auto rounded border bg-raised p-2 shadow-lg ${
        error ? "border-critical/50" : "border-border-strong"
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
