import { describe, expect, it } from "vitest";
import { archiveBase, entraConfig } from "./config";

const COMPLETE = {
  VITE_ENTRA_CLIENT_ID: "client",
  VITE_ENTRA_TENANT_ID: "tenant",
  VITE_ENTRA_SCOPE_POLYMARKET: "api://tradingcenter-polymarket-data/access_as_user",
} as unknown as ImportMetaEnv;

describe("where the archive answers", () => {
  it("keeps a relative path as it is, minus the slash callers join onto", () => {
    expect(archiveBase("/polymarket-api/")).toBe("/polymarket-api");
    expect(archiveBase(undefined)).toBe("/polymarket-api");
  });
});

describe("the sign-in configuration", () => {
  it("is all three values or none of them", () => {
    expect(entraConfig(COMPLETE)).toEqual({
      clientId: "client",
      tenantId: "tenant",
      scope: "api://tradingcenter-polymarket-data/access_as_user",
    });
  });

  it("is nothing at all when one is missing, rather than a sign-in that cannot finish", () => {
    const partial = { ...COMPLETE, VITE_ENTRA_SCOPE_POLYMARKET: "" } as unknown as ImportMetaEnv;
    expect(entraConfig(partial)).toBeNull();
    expect(entraConfig({} as unknown as ImportMetaEnv)).toBeNull();
  });
});
