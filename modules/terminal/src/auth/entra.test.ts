import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EntraConfig } from "../data/config";
import { SignedOut, type IdentityState } from "./identity";

/**
 * One session, one `Identity` per back end — the property `terminal-identity` asks for
 * ("Dwa moduły o różnych publicznościach") and the one this file existed to break until
 * 22 August 2026: the terminal took a single token with the archive's audience and sent
 * it to every module, and the gateway had been configured to accept it.
 *
 * MSAL is stood in for rather than run: what is under test is which scope each identity
 * asks for, not that Microsoft's library can fetch a token.
 */

const acquireTokenSilent = vi.fn();
const loginRedirect = vi.fn();
const setActiveAccount = vi.fn();
const account = { homeAccountId: "an-account" };

vi.mock("@azure/msal-browser", async () => {
  const actual =
    await vi.importActual<typeof import("@azure/msal-browser")>("@azure/msal-browser");
  return {
    ...actual,
    PublicClientApplication: class {
      initialize = () => Promise.resolve();
      handleRedirectPromise = () => Promise.resolve({ account });
      getActiveAccount = () => account;
      getAllAccounts = () => [account];
      setActiveAccount = setActiveAccount;
      acquireTokenSilent = acquireTokenSilent;
      loginRedirect = loginRedirect;
    },
  };
});

const { createEntraIdentities } = await import("./entra");

const config: EntraConfig = {
  clientId: "a-client-id",
  tenantId: "a-tenant-id",
  scopes: {
    archive: "api://archive/access_as_user",
    workbench: "api://workbench/access_as_user",
    gateway: "api://gateway/access_as_user",
    polymarket: "api://polymarket/access_as_user",
  },
};

beforeEach(() => {
  acquireTokenSilent.mockReset();
  loginRedirect.mockReset();
  acquireTokenSilent.mockImplementation(({ scopes }: { scopes: string[] }) =>
    Promise.resolve({ accessToken: `token-for:${scopes[0]}` }),
  );
});

async function signedIn() {
  const identities = createEntraIdentities(config);
  await identities.initialize();
  return identities;
}

describe("createEntraIdentities", () => {
  it("asks for the audience of the module being called, one per back end", async () => {
    const identities = await signedIn();

    await expect(identities.for(config.scopes.polymarket).token()).resolves.toBe(
      "token-for:api://polymarket/access_as_user",
    );
    await expect(identities.for(config.scopes.workbench).token()).resolves.toBe(
      "token-for:api://workbench/access_as_user",
    );
    await expect(identities.shared.token()).resolves.toBe("token-for:api://archive/access_as_user");
  });

  it("never sends one module's token to another", async () => {
    const identities = await signedIn();

    const forGateway = await identities.for(config.scopes.gateway).token();

    expect(forGateway).not.toBe("token-for:api://archive/access_as_user");
    expect(acquireTokenSilent).toHaveBeenCalledWith(
      expect.objectContaining({ scopes: ["api://gateway/access_as_user"] }),
    );
  });

  it("gives a back end with no scope the no-credential identity, not somebody else's", async () => {
    const identities = await signedIn();

    await expect(identities.for(null).token()).resolves.toBeNull();
    expect(acquireTokenSilent).not.toHaveBeenCalled();
  });

  it("shares one sign-in across every module's identity", async () => {
    const identities = await signedIn();

    expect(identities.for(config.scopes.polymarket).state()).toBe("signed-in");
    expect(identities.shared.state()).toBe("signed-in");

    // There is one operator and one session, so a sign-out discovered while asking for
    // *one* audience reaches a subscriber watching another. Four sessions would leave the
    // shell reporting signed-in until whichever module it happened to watch was called.
    const seen: IdentityState[] = [];
    identities.for(config.scopes.gateway).subscribe((state) => seen.push(state));
    acquireTokenSilent.mockRejectedValueOnce(new InteractionRequiredAuthError("interaction_required", "sign in again"));

    await expect(identities.shared.token()).rejects.toBeInstanceOf(SignedOut);
    expect(seen).toEqual(["signed-out"]);
    expect(identities.for(config.scopes.polymarket).state()).toBe("signed-out");
  });

  it("asks the redirect for one resource, and the rest silently", async () => {
    const identities = await signedIn();

    identities.shared.signIn();

    expect(loginRedirect).toHaveBeenCalledWith({ scopes: [config.scopes.archive] });
  });

  it("refreshes on the same audience it first asked for", async () => {
    const identities = await signedIn();

    await identities.for(config.scopes.polymarket).refresh();

    expect(acquireTokenSilent).toHaveBeenCalledWith(
      expect.objectContaining({ scopes: [config.scopes.polymarket], forceRefresh: true }),
    );
  });
});
