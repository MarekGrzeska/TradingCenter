/**
 * Reading `window.localStorage` throws outright in private-mode Safari and with third-party storage blocked,
 * and there is no `window` in a test. `null` rather than a stub: every caller already has a "nothing saved" path.
 */
export function safeLocalStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
