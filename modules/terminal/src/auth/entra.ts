import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import type { EntraConfig } from "../data/config";
import {
  createListeners,
  noIdentity,
  SignedOut,
  type Identity,
  type IdentityState,
} from "./identity";

/**
 * The only file that knows Entra exists; everything else takes an `Identity` and asks it
 * for a token.
 *
 * **One session, one `Identity` per module.** Every back end this terminal calls stands
 * behind its own gate and accepts a token minted for its own audience, so `for(scope)`
 * hands out an `Identity` bound to one of them. They share the account, the state and the
 * listeners — there is one operator signed in, not four — and differ only in what they
 * ask Entra for. Until 22 August 2026 there was one token with the archive's audience,
 * sent to all three back ends, and the gateway had been configured to accept it; the
 * pre-authorizations for asking by name had been standing unused since (`infra/entra.tf`).
 *
 * Redirect, not a popup: a popup dies under a blocker and leaves an operator staring at
 * a terminal that will not load. The full page load it costs is affordable — the grid
 * layout is in `localStorage` and MSAL returns to the address it left from.
 *
 * `sessionStorage`, because memory would send the operator through sign-in on every
 * reload and `localStorage` would keep the account after the tab is closed.
 */
export interface EntraIdentities {
  /** Resolves the redirect the operator is arriving back from. Called once, by
   *  `main.tsx`, before the app mounts. */
  initialize(): Promise<void>;
  /** An `Identity` for one module's audience. `null` — the module has no scope
   *  configured — gives the no-credential identity rather than somebody else's token. */
  for(scope: string | null): Identity;
  /** The shared sign-in state, for the shell. Any module's identity would answer the
   *  same; this one is named so nothing has to pick a module to ask. */
  shared: Identity;
}

export function createEntraIdentities(config: EntraConfig): EntraIdentities {
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

  async function acquire(scope: string, forceRefresh: boolean): Promise<string> {
    if (!account) throw new SignedOut();
    try {
      const result = await msal.acquireTokenSilent({
        scopes: [scope],
        account,
        forceRefresh,
      });
      moveTo("signed-in");
      return result.accessToken;
    } catch (cause) {
      // The account itself is gone: there is no session, whichever module was being asked
      // for. This one really is a sign-out.
      if (cause instanceof BrowserAuthError && cause.errorCode === "no_account_error") {
        adopt(null);
        throw new SignedOut();
      }

      // Interaction required is **per resource** now that each module has its own audience.
      // Dropping the shared account here would mean a missing consent for one back end
      // signing the operator out of the whole terminal — a tab they never opened taking the
      // chart down with it. Only the scope the session was established against says
      // anything about the session.
      if (cause instanceof InteractionRequiredAuthError) {
        if (scope === config.scopes.archive) {
          adopt(null);
          throw new SignedOut();
        }
        throw cause;
      }

      // Anything else — a network blip on the token endpoint — is not a signed-out session
      // and must not be reported as one, or a flaky minute would send somebody through a
      // sign-in they did not need.
      throw cause;
    }
  }

  /** Everything except the token is shared: one operator, one session, one state. */
  function identityFor(scope: string): Identity {
    return {
      state: () => state,
      subscribe: listeners.add,
      token: () => acquire(scope, false),
      refresh: () => acquire(scope, true),
      signIn,
    };
  }

  function signIn(): void {
    // The archive's scope, because sign-in has to name one resource and this is the one
    // every deployment configures. The rest are acquired silently afterwards, which the
    // pre-authorizations in `infra/entra.tf` are what make possible without a second
    // consent screen.
    void msal.loginRedirect({ scopes: [config.scopes.archive] });
  }

  return {
    initialize,
    for: (scope) => (scope === null ? noIdentity : identityFor(scope)),
    shared: identityFor(config.scopes.archive),
  };
}
