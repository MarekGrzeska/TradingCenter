import {
  BrowserAuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import type { EntraConfig } from "../data/config";
import { SignedOut, type Identity, type IdentityState } from "./identity";

/**
 * The only file here that knows Entra exists. One audience, unlike the terminal's four: this app reads
 * `polymarket-data` and nothing else, so there is no per-resource consent to keep apart.
 *
 * Redirect rather than popup, and `sessionStorage` rather than `localStorage`: a phone browser blocks
 * popups by default, and a token left in local storage outlives the tab it was minted for.
 */
export interface EntraIdentity {
  /** Resolves the redirect the operator is arriving back from. Called once, before the app mounts:
   *  a token asked for mid-redirect belongs to nobody yet. */
  initialize(): Promise<void>;
  identity: Identity;
}

export function createEntraIdentity(config: EntraConfig): EntraIdentity {
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
      // The two shapes of "there is no session any more". Anything else — a network blip on the token
      // endpoint — is not a signed-out operator and must not send one through a sign-in they did not need.
      const gone =
        (cause instanceof BrowserAuthError && cause.errorCode === "no_account_error") ||
        cause instanceof InteractionRequiredAuthError;
      if (gone) {
        adopt(null);
        throw new SignedOut();
      }
      throw cause;
    }
  }

  return {
    async initialize() {
      await msal.initialize();
      const redirect = await msal.handleRedirectPromise();
      adopt(redirect?.account ?? msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null);
    },
    identity: {
      state: () => state,
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      token: () => acquire(false),
      refresh: () => acquire(true),
      signIn: () => void msal.loginRedirect({ scopes: [config.scope] }),
    },
  };
}
