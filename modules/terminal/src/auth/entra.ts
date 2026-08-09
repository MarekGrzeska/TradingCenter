import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import type { EntraConfig } from "../data/config";
import { createListeners, SignedOut, type Identity, type IdentityState } from "./identity";

/**
 * The only file that knows Entra exists; everything else takes an `Identity` and asks it
 * for a token.
 *
 * Redirect, not a popup: a popup dies under a blocker and leaves an operator staring at
 * a terminal that will not load. The full page load it costs is affordable — the grid
 * layout is in `localStorage` and MSAL returns to the address it left from.
 *
 * `sessionStorage`, because memory would send the operator through sign-in on every
 * reload and `localStorage` would keep the account after the tab is closed.
 */
export function createEntraIdentity(config: EntraConfig): Identity {
  const listeners = createListeners();

  const msal = new PublicClientApplication({
    auth: {
      clientId: config.clientId,
      authority: `https://login.microsoftonline.com/${config.tenantId}`,
      // Spelled out rather than left to MSAL's default of
      // `window.location.origin`, which has no trailing slash — and Azure will
      // not register a redirect URI without one when there is no path segment
      // (`infra/entra.tf`). The two have to be the same string, and only one of
      // them can be registered.
      redirectUri: `${window.location.origin}/`,
    },
    cache: { cacheLocation: "sessionStorage" },
  });

  let account: AccountInfo | null = null;
  let state: IdentityState = "signed-out";

  function moveTo(next: IdentityState): void {
    if (next === state) return;
    state = next;
    listeners.notify(state);
  }

  function adopt(next: AccountInfo | null): void {
    account = next;
    if (next) msal.setActiveAccount(next);
    moveTo(next ? "signed-in" : "signed-out");
  }

  /** Resolves the redirect the operator is arriving back from, if they are, and
   *  otherwise picks up a session already in `sessionStorage`.
   *
   *  Must finish before the app mounts. The first render subscribes to candles,
   *  which asks for a token, and a token asked for mid-redirect belongs to
   *  nobody yet. */
  async function initialize(): Promise<void> {
    await msal.initialize();
    const redirect = await msal.handleRedirectPromise();
    adopt(redirect?.account ?? msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null);
  }

  async function acquire(forceRefresh: boolean): Promise<string> {
    if (!account) throw new SignedOut();
    try {
      const result = await msal.acquireTokenSilent({
        scopes: [config.scope],
        account,
        forceRefresh,
      });
      moveTo("signed-in");
      return result.accessToken;
    } catch (cause) {
      // The two MSAL spells for "this cannot be fixed without the operator".
      // Anything else — a network blip on the token endpoint — is not a signed-out
      // session and must not be reported as one, or a flaky minute would send
      // somebody through a sign-in they did not need.
      if (
        cause instanceof InteractionRequiredAuthError ||
        (cause instanceof BrowserAuthError && cause.errorCode === "no_account_error")
      ) {
        adopt(null);
        throw new SignedOut();
      }
      throw cause;
    }
  }

  return {
    state: () => state,
    subscribe: listeners.add,
    token: () => acquire(false),
    refresh: () => acquire(true),
    signIn: () => {
      void msal.loginRedirect({ scopes: [config.scope] });
    },
    // Not part of `Identity`: only `main.tsx` calls it, once, and putting it on
    // the interface would oblige every stand-in in a test to implement it.
    initialize,
  } as Identity & { initialize: () => Promise<void> };
}
