/**
 * The terminal's one way of saying something that is not attached to a place on screen.
 *
 * A store rather than a context, for the same reason `gridStore` is one: what raises a
 * toast is usually an effect deep in a chart slot, and threading a provider down to it
 * buys nothing over calling a function. `Toaster` is mounted once in `Shell` and reads
 * this; nothing else renders toasts (`toastsComeFromOnePlace.test.ts`).
 */

export type ToastSeverity = "error" | "info";

export interface Toast {
  id: number;
  /** Identity across repeats. A chart requeries its indicators on every candle close, so
   *  the same refusal arrives again and again — the same key updates the toast already on
   *  screen and restarts its clock rather than stacking a fourth copy of it. */
  key: string;
  severity: ToastSeverity;
  title: string;
  /** What the server actually said, when there is one. Kept apart from `title` because it
   *  is the part worth reading twice, and the part nobody can guess. */
  detail?: string;
}

export interface ToastInput {
  key: string;
  severity?: ToastSeverity;
  title: string;
  detail?: string;
}

export interface ToastStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): readonly Toast[];
  show(toast: ToastInput): void;
  dismiss(id: number): void;
  /** Test seam. Nothing in the app clears everything at once — a toast the operator has
   *  not read is not the app's to take away. */
  clear(): void;
}

/** How long a toast stays before it removes itself. An error carries a detail that takes
 *  a moment to read and may be the only place that detail appears; an info line is an
 *  acknowledgement and is gone before it is in the way. */
export const DISMISS_AFTER_MS: Record<ToastSeverity, number> = {
  error: 12_000,
  info: 5_000,
};

/** At most this many on screen; the oldest goes first. A burst that fills the panel hides
 *  the chart it is talking about, which is the opposite of the point. */
const MAX_VISIBLE = 4;

type Timers = Pick<typeof globalThis, "setTimeout" | "clearTimeout">;

export function createToastStore(timers: Timers = globalThis): ToastStore {
  let toasts: readonly Toast[] = [];
  let nextId = 1;
  const listeners = new Set<() => void>();
  const timeouts = new Map<number, ReturnType<typeof setTimeout>>();

  function commit(next: readonly Toast[]): void {
    toasts = next;
    for (const listener of listeners) listener();
  }

  function cancelTimer(id: number): void {
    const handle = timeouts.get(id);
    if (handle !== undefined) {
      timers.clearTimeout(handle);
      timeouts.delete(id);
    }
  }

  function scheduleDismissal(toast: Toast): void {
    cancelTimer(toast.id);
    timeouts.set(
      toast.id,
      timers.setTimeout(() => dismiss(toast.id), DISMISS_AFTER_MS[toast.severity]),
    );
  }

  function dismiss(id: number): void {
    cancelTimer(id);
    if (!toasts.some((toast) => toast.id === id)) return;
    commit(toasts.filter((toast) => toast.id !== id));
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    getSnapshot: () => toasts,

    show({ key, severity = "info", title, detail }) {
      const existing = toasts.find((toast) => toast.key === key);
      if (existing) {
        // Same id, so React keeps the element it already has and the toast does not
        // flicker out and back in while the same thing keeps failing.
        const updated: Toast = { ...existing, severity, title, detail };
        commit(toasts.map((toast) => (toast.id === existing.id ? updated : toast)));
        scheduleDismissal(updated);
        return;
      }

      const toast: Toast = { id: nextId++, key, severity, title, detail };
      const kept = [...toasts, toast].slice(-MAX_VISIBLE);
      for (const dropped of toasts.filter((t) => !kept.includes(t))) cancelTimer(dropped.id);
      commit(kept);
      scheduleDismissal(toast);
    },

    dismiss,

    clear() {
      for (const toast of toasts) cancelTimer(toast.id);
      commit([]);
    },
  };
}

export const toastStore = createToastStore();

/** What callers use. A free function on purpose: an effect that has just caught something
 *  should not have to have asked for a hook first. */
export function showToast(toast: ToastInput): void {
  toastStore.show(toast);
}
