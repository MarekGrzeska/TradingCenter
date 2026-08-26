import type { Identity } from "./identity";

/**
 * Sending the operator to sign in unasked, because a terminal with no identity shows nothing. The whole risk is the
 * redirect loop, hence this marker — in `sessionStorage`, since the redirect is a full page load and it dies with the tab.
 */
export const SIGN_IN_ATTEMPTED_KEY = "tc.terminal.sign-in-attempted";

export function startSignInIfNeeded(
  identity: Identity,
  storage: Storage | null = safeSessionStorage(),
): boolean {
  // No identity configured is not "signed out": it is local work against an
  // archive with nothing in front of it, and there is nowhere to send anybody.
  if (identity.state() === "unconfigured") return false;

  if (identity.state() === "signed-in") {
    // A fresh session ends the previous attempt's story — the next time this
    // one expires, the terminal may try again.
    storage?.removeItem(SIGN_IN_ATTEMPTED_KEY);
    return false;
  }

  // Without storage there is no way to remember an attempt, and so no way to stop at one. Not signing in
  // is the safe answer, and the operator still has the button.
  if (!storage) return false;

  if (storage.getItem(SIGN_IN_ATTEMPTED_KEY) !== null) return false;

  storage.setItem(SIGN_IN_ATTEMPTED_KEY, "1");
  identity.signIn();
  return true;
}

function safeSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    // Blocked by the browser — third-party context, hardened settings. Not an
    // error worth showing: it only means the terminal will ask rather than act.
    return null;
  }
}
