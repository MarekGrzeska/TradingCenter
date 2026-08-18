/**
 * The browser's storage, or nothing.
 *
 * Three stores reached for `window.localStorage` behind the same six lines of guard, and
 * all three needed it: reading the property throws outright in private-mode Safari and
 * with third-party storage blocked, and there is no `window` at all when a module is
 * imported by a test that renders nothing. A terminal that will not start because a
 * layout could not be remembered is the worse failure by a distance.
 *
 * `null` rather than a stub: every caller here already has a "nothing was saved" path —
 * defaults, an empty conversation list, a cursor at zero — and a stub that silently
 * forgets everything would be a fourth thing to keep in step.
 */
export function safeLocalStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
