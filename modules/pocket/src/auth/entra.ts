import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import type { EntraConfig } from "../data/config";
import { noIdentity, SignedOut, type Identity, type IdentityState } from "./identity";

/**
 * The only file here that knows Entra exists. One `Identity` per audience, sharing the account and the
 * state: each back end accepts a token minted for its own audience and no other.
 *
 * Redirect rather than popup, and `sessionStorage` rather than `localStorage`: a phone browser blocks
 * popups by default, and a token left in local storage outlives the tab it was minted for.
 */
export interface EntraIdentities {
  /** Resolves the redirect the operator is arriving back from. Called once, before the app mounts: a
   *  token asked for mid-redirect belongs to nobody yet. */
  initialize(): Promise<void>;
  /** The archive's, and the whole app's sign-in state — it is the audience sign-in names. */
  archive: Identity;
  /** The conversation's. `noIdentity` when no scope is configured for it, which sends requests bare
   *  rather than carrying the archive's token to a module that would refuse it. */
  workbench: Identity;
  /** The post archive's, on the same terms as the conversation's. */
  posts: Identity;
}

export function createEntraIdentities(config: EntraConfig): EntraIdentities {
  const listeners = new Set<(state: IdentityState) => void>();

  const msal = new PublicClientApplication({
    auth: {
      clientId: config.clientId,
      authority: `https://login.microsoftonline.com/${config.tenantId}`,
      // Spelled out rather than left to MSAL's default, which has no trailing slash — and Azure will
      // not register a redirect URI without one when there is no path segment.
      redirectUri: `${window.location.origin}/`,
    },
    cache: { cacheLocation: "sessionStorage" },
  });

  let account: AccountInfo | null = null;
  let state: IdentityState = "signed-out";

  function moveTo(next: IdentityState): void {
    if (next === state) return;
    state = next;
    for (const listener of listeners) listener(state);
  }

  function adopt(next: AccountInfo | null): void {
    account = next;
    if (next) msal.setActiveAccount(next);
    moveTo(next ? "signed-in" : "signed-out");
  }

  async function acquire(scope: string, forceRefresh: boolean): Promise<string> {
    if (!account) throw new SignedOut();
    try {
      const result = await msal.acquireTokenSilent({ scopes: [scope], account, forceRefresh });
      moveTo("signed-in");
      return result.accessToken;
    } catch (cause) {
      // The account itself is gone: there is no session, whichever audience was being asked for.
      if (cause instanceof BrowserAuthError && cause.errorCode === "no_account_error") {
        adopt(null);
        throw new SignedOut();
      }

      // Interaction required is **per resource**. Dropping the shared account for the conversation's
      // audience would sign the operator out of the archive over a consent the archive never needed.
      if (cause instanceof InteractionRequiredAuthError) {
        if (scope === config.scopes.archive) {
          adopt(null);
          throw new SignedOut();
        }
        throw cause;
      }

      // Anything else — a network blip on the token endpoint — is not a signed-out session, and
      // reporting it as one would send somebody through a sign-in they did not need.
      throw cause;
    }
  }

  function identityFor(scope: string): Identity {
    return {
      state: () => state,
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      token: () => acquire(scope, false),
      refresh: () => acquire(scope, true),
      // The archive's scope, because sign-in has to name one resource and this is the one every
      // deployment configures. The other is acquired silently, which the pre-authorization allows.
      signIn: () => void msal.loginRedirect({ scopes: [config.scopes.archive] }),
    };
  }

  return {
    async initialize() {
      await msal.initialize();
      const redirect = await msal.handleRedirectPromise();
      adopt(redirect?.account ?? msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null);
    },
    archive: identityFor(config.scopes.archive),
    workbench:
      config.scopes.workbench === null ? noIdentity : identityFor(config.scopes.workbench),
    posts: config.scopes.posts === null ? noIdentity : identityFor(config.scopes.posts),
  };
}
