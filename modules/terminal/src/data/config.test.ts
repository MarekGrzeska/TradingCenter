import { describe, expect, it } from "vitest";
import { TABS } from "../app/tabs";
import { resolveEndpoints, resolveEntra, resolveHttpBase, resolveWsBase } from "./config";

describe("resolveHttpBase", () => {
  it("passes a relative path through, trimmed", () => {
    expect(resolveHttpBase("/api/")).toBe("/api");
  });

  it("passes a full URL through, trimmed", () => {
    expect(resolveHttpBase("https://gateway.example.com/")).toBe("https://gateway.example.com");
  });
});

describe("resolveWsBase", () => {
  const httpLoc = { protocol: "http:", host: "localhost:5173" };
  const httpsLoc = { protocol: "https:", host: "terminal.example.com" };

  it("expands a relative path against the page origin, using ws for http pages", () => {
    expect(resolveWsBase("/ws", httpLoc)).toBe("ws://localhost:5173/ws");
  });

  it("expands a relative path using wss for https pages", () => {
    expect(resolveWsBase("/ws", httpsLoc)).toBe("wss://terminal.example.com/ws");
  });

  it("adds a leading slash to a relative path missing one", () => {
    expect(resolveWsBase("ws", httpLoc)).toBe("ws://localhost:5173/ws");
  });

  it("passes an absolute ws(s) URL through unchanged", () => {
    expect(resolveWsBase("wss://gateway.example.com/stream", httpLoc)).toBe(
      "wss://gateway.example.com/stream",
    );
  });

  it("corrects an absolute http(s) URL's scheme instead of failing later", () => {
    expect(resolveWsBase("https://gateway.example.com/stream", httpLoc)).toBe(
      "wss://gateway.example.com/stream",
    );
    expect(resolveWsBase("http://gateway.example.com/stream", httpLoc)).toBe(
      "ws://gateway.example.com/stream",
    );
  });
});

describe("resolveEndpoints", () => {
  const devLoc = { protocol: "http:", host: "localhost:5173" };

  it("resolves every address independently from env", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_ARCHIVE_HTTP: "/archive-api",
        VITE_ARCHIVE_WS: "/archive-api/ws",
        VITE_WORKBENCH_HTTP: "/workbench-api",
        VITE_GATEWAY_HTTP: "/gateway-api",
        VITE_POLYMARKET_HTTP: "/polymarket-api",
      },
      devLoc,
    );
    expect(endpoints).toEqual({
      archiveHttp: "/archive-api",
      archiveWs: "ws://localhost:5173/archive-api/ws",
      workbenchHttp: "/workbench-api",
      gatewayHttp: "/gateway-api",
      polymarketHttp: "/polymarket-api",
    });
  });

  it("resolves a fully split topology — static site, archive and workbench on three hosts", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_ARCHIVE_HTTP: "https://archive.example.com",
        VITE_ARCHIVE_WS: "wss://archive.example.com/ws",
        VITE_WORKBENCH_HTTP: "https://workbench.example.com",
        VITE_GATEWAY_HTTP: "https://gateway.example.com",
        VITE_POLYMARKET_HTTP: "https://polymarket.example.com",
      },
      { protocol: "https:", host: "terminal.example.com" },
    );
    expect(endpoints).toEqual({
      archiveHttp: "https://archive.example.com",
      archiveWs: "wss://archive.example.com/ws",
      workbenchHttp: "https://workbench.example.com",
      gatewayHttp: "https://gateway.example.com",
      polymarketHttp: "https://polymarket.example.com",
    });
  });

  it("falls back to the dev-proxy prefixes when the env vars are unset, instead of throwing", () => {
    expect(resolveEndpoints({}, devLoc)).toEqual({
      archiveHttp: "/archive-api",
      archiveWs: "ws://localhost:5173/archive-api/ws",
      workbenchHttp: "/workbench-api",
      gatewayHttp: "/gateway-api",
      polymarketHttp: "/polymarket-api",
    });
  });

  // Caught in a browser, not here: the archive answered on `/archive`, which is
  // also the Archive tab's route, so reloading the tab returned the service's
  // JSON instead of the app. Clicking through worked — the router never asks a
  // server — which is why nothing in this suite noticed.
  //
  // The relative prefix is only safe if no tab claims it, so it is compared
  // against the route list rather than eyeballed. Covers the workbench's and the
  // gateway's prefixes too, since both are relative defaults of the same shape — and the
  // gateway's is the one that would have collided: there is an `accounts` tab now, and
  // `/accounts` would have shadowed it exactly the way `/archive` once did.
  it("gives no back end a relative prefix that a tab route already claims", () => {
    const { archiveHttp, archiveWs, workbenchHttp, gatewayHttp, polymarketHttp } =
      resolveEndpoints({}, devLoc);
    const routes = new Set(TABS.map((tab) => tab.path));

    const prefixes = [
      archiveHttp,
      new URL(archiveWs).pathname,
      workbenchHttp,
      gatewayHttp,
      polymarketHttp,
    ]
      .filter((base) => base.startsWith("/"))
      .map((base) => base.split("/")[1]);

    expect(prefixes.length).toBeGreaterThan(0);
    for (const prefix of prefixes) {
      expect(routes.has(prefix)).toBe(false);
    }
  });
});

describe("resolveEntra", () => {
  const complete = {
    VITE_ENTRA_CLIENT_ID: "a-client-id",
    VITE_ENTRA_TENANT_ID: "a-tenant-id",
    VITE_ENTRA_SCOPE: "api://market-data/access_as_user",
  };

  it("reads the three values when they are all there", () => {
    expect(resolveEntra(complete)).toEqual({
      clientId: "a-client-id",
      tenantId: "a-tenant-id",
      scopes: {
        archive: "api://market-data/access_as_user",
        workbench: null,
        gateway: null,
        polymarket: null,
      },
    });
  });

  it("reads a scope per back end when each is configured", () => {
    expect(
      resolveEntra({
        ...complete,
        VITE_ENTRA_SCOPE_WORKBENCH: "api://agent/access_as_user",
        VITE_ENTRA_SCOPE_GATEWAY: "api://gateway/access_as_user",
        VITE_ENTRA_SCOPE_POLYMARKET: "api://polymarket/access_as_user",
      })?.scopes,
    ).toEqual({
      archive: "api://market-data/access_as_user",
      workbench: "api://agent/access_as_user",
      gateway: "api://gateway/access_as_user",
      polymarket: "api://polymarket/access_as_user",
    });
  });

  // The rule the split exists for: a module with no scope of its own is called with no
  // credential, not with the archive's. Falling back would be the terminal telling four
  // gates the same thing, which is what this change stopped
  // (specs/terminal-identity, "Dwa moduły o różnych publicznościach").
  it("does not fall back to the archive's scope for a back end with none", () => {
    const scopes = resolveEntra({ ...complete, VITE_ENTRA_SCOPE_GATEWAY: "api://gw/access" })
      ?.scopes;

    expect(scopes?.gateway).toBe("api://gw/access");
    expect(scopes?.workbench).toBeNull();
    expect(scopes?.polymarket).toBeNull();
  });

  it("reads a blank per-module scope as unset rather than as an empty audience", () => {
    expect(resolveEntra({ ...complete, VITE_ENTRA_SCOPE_POLYMARKET: "   " })?.scopes.polymarket)
      .toBeNull();
  });

  // Not a misconfiguration: locally the archive has nothing in front of it, and
  // a terminal that demanded a tenant before it would start would make `pnpm
  // dev` depend on Azure.
  it("answers with no identity when none is configured", () => {
    expect(resolveEntra({})).toBeNull();
  });

  it("refuses a partial set rather than half-signing anybody in", () => {
    // Two out of three is a typo. Starting anyway turns it into a sign-in that
    // fails much later with a message about audiences, a long way from the line
    // that caused it.
    expect(() => resolveEntra({ VITE_ENTRA_CLIENT_ID: "a-client-id" })).toThrow(/together/);
    expect(() =>
      resolveEntra({ ...complete, VITE_ENTRA_SCOPE: "   " }),
    ).toThrow(/together/);
  });
});
