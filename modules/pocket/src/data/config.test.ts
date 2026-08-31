import { describe, expect, it } from "vitest";
import { archiveBase, entraConfig, postsBase, workbenchBase } from "./config";

const COMPLETE = {
  VITE_ENTRA_CLIENT_ID: "client",
  VITE_ENTRA_TENANT_ID: "tenant",
  VITE_ENTRA_SCOPE_POLYMARKET: "api://tradingcenter-polymarket-data/access_as_user",
} as unknown as ImportMetaEnv;

describe("where each back end answers", () => {
  it("keeps a relative path as it is, minus the slash callers join onto", () => {
    expect(archiveBase("/polymarket-api/")).toBe("/polymarket-api");
    expect(archiveBase(undefined)).toBe("/polymarket-api");
    expect(workbenchBase(undefined)).toBe("/workbench-api");
    expect(postsBase(undefined)).toBe("/social-api");
  });
});

describe("the sign-in configuration", () => {
  it("is the client, the tenant and the archive's scope, or none of them", () => {
    expect(entraConfig(COMPLETE)).toEqual({
      clientId: "client",
      tenantId: "tenant",
      scopes: {
        archive: "api://tradingcenter-polymarket-data/access_as_user",
        workbench: null,
        posts: null,
      },
    });
  });

  it("is nothing at all when one is missing, rather than a sign-in that cannot finish", () => {
    const partial = { ...COMPLETE, VITE_ENTRA_SCOPE_POLYMARKET: "" } as unknown as ImportMetaEnv;
    expect(entraConfig(partial)).toBeNull();
    expect(entraConfig({} as unknown as ImportMetaEnv)).toBeNull();
  });

  it("carries the conversation's audience separately, and its absence is a working build", () => {
    const withAgent = {
      ...COMPLETE,
      VITE_ENTRA_SCOPE_WORKBENCH: "api://tradingcenter-agent/access_as_user",
    } as unknown as ImportMetaEnv;

    expect(entraConfig(withAgent)?.scopes.workbench).toBe(
      "api://tradingcenter-agent/access_as_user",
    );
    // A token minted for the archive is never sent to the workbench, so the agent goes without one
    // rather than borrowing it.
    expect(entraConfig(COMPLETE)?.scopes.workbench).toBeNull();
  });

  it("carries the post archive's audience on the same terms", () => {
    const withPosts = {
      ...COMPLETE,
      VITE_ENTRA_SCOPE_SOCIAL: "api://tradingcenter-social-data/access_as_user",
    } as unknown as ImportMetaEnv;

    expect(entraConfig(withPosts)?.scopes.posts).toBe(
      "api://tradingcenter-social-data/access_as_user",
    );
    expect(entraConfig(COMPLETE)?.scopes.posts).toBeNull();
  });
});
