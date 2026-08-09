import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import type { EntraConfig } from "../data/config";
import { createListeners, SignedOut, type Identity, type IdentityState } from "./identity";

/**
 * The only file that knows Entra exists.
 *
 * Everything else takes an `Identity` (`identity.ts`) and asks it for a token.
 * That seam is not ceremony: it is what lets the data layer's tests describe a
 * signed-out operator in two lines instead of standing up a sign-in flow, and
 * it is what would make swapping the provider a change to one file.
 *
 * **Redirect, not a popup.** A popup dies under a blocker and leaves an
 * operator staring at a terminal that will not load, with nothing on screen
 * saying why. A redirect costs a full page load, which the terminal can afford:
 * the grid layout lives in `localStorage` (`gridStore.ts`), and MSAL returns to
 * the address it left from, so the operator comes back to the view they were
 * on.
 *
 * **`sessionStorage`, not memory and not `localStorage`.** Memory would lose
 * the account on every reload and send the operator through sign-in each time;
 * `localStorage` would keep it after the tab is closed. Surviving a reload and
 * dying with the tab is the right shape for a terminal.
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
