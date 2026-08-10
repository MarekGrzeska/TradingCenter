import type { Identity } from "./identity";

/**
 * Sending the operator to sign in without being asked to: a terminal with no identity
 * shows no candle, no instrument and no history (`terminal-identity` spec, "Operator
 * loguje się kontem organizacji").
 *
 * The whole risk is the redirect loop, the one failure an operator cannot break out of.
 * Hence this marker, written *before* the page leaves, so a return that finds it means
 * "already tried once" and the terminal stays put with a button. `sessionStorage`
 * because the redirect is a full page load that module memory does not survive, and it
 * dies with the tab — where MSAL keeps its own session, for the same reason.
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
