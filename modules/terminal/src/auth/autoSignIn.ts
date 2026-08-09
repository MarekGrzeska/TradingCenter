import type { Identity } from "./identity";

/**
 * Sending the operator to sign in without being asked to.
 *
 * A terminal with no identity shows no candle, no instrument and no history, so
 * waiting for the operator to find a button in the corner asks them to guess the
 * one thing that has to happen anyway (`terminal-identity` spec, "Operator loguje
 * się kontem organizacji").
 *
 * The whole risk of doing this is the redirect loop, which is the one failure an
 * operator cannot break out of: a page that sends itself back to sign-in after
 * every unsuccessful return can be neither read nor recovered. Hence the marker
 * — written *before* the page leaves, so a return that finds it there means "we
 * already tried this once", and the terminal stays put with its own signed-out
 * state and a button.
 *
 * `sessionStorage` rather than a module variable, because the redirect is a full
 * page load and module memory does not survive it. It dies with the tab, which
 * is the right lifetime — and it is where MSAL keeps its own session, for the
 * same reason.
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

  // Without storage there is no way to remember an attempt, and without that
  // there is no way to stop at one. Not signing in at all is the safe answer;
  // the operator still has the button. (MSAL caches its session in the same
  // place, so this is a terminal that could not stay signed in anyway.)
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
