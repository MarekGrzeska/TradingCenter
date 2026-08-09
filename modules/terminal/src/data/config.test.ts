import { describe, expect, it } from "vitest";
import { TABS } from "../app/tabs";
import { resolveEndpoints, resolveHttpBase, resolveWsBase } from "./config";

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

  it("resolves both addresses independently from env", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_ARCHIVE_HTTP: "/archive-api",
        VITE_ARCHIVE_WS: "/archive-api/ws",
      },
      devLoc,
    );
    expect(endpoints).toEqual({
      archiveHttp: "/archive-api",
      archiveWs: "ws://localhost:5173/archive-api/ws",
    });
  });

  it("resolves a fully split topology — static site and archive on two hosts", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_ARCHIVE_HTTP: "https://archive.example.com",
        VITE_ARCHIVE_WS: "wss://archive.example.com/ws",
      },
      { protocol: "https:", host: "terminal.example.com" },
    );
    expect(endpoints).toEqual({
      archiveHttp: "https://archive.example.com",
      archiveWs: "wss://archive.example.com/ws",
    });
  });

  it("falls back to the dev-proxy prefix when the env vars are unset, instead of throwing", () => {
    expect(resolveEndpoints({}, devLoc)).toEqual({
      archiveHttp: "/archive-api",
      archiveWs: "ws://localhost:5173/archive-api/ws",
    });
  });

  // Caught in a browser, not here: the archive answered on `/archive`, which is
  // also the Archive tab's route, so reloading the tab returned the service's
  // JSON instead of the app. Clicking through worked — the router never asks a
  // server — which is why nothing in this suite noticed.
  //
  // The relative prefix is only safe if no tab claims it, so it is compared
  // against the route list rather than eyeballed.
  it("gives the archive no relative prefix that a tab route already claims", () => {
    const { archiveHttp, archiveWs } = resolveEndpoints({}, devLoc);
    const routes = new Set(TABS.map((tab) => tab.path));

    const prefixes = [archiveHttp, new URL(archiveWs).pathname]
      .filter((base) => base.startsWith("/"))
      .map((base) => base.split("/")[1]);

    expect(prefixes.length).toBeGreaterThan(0);
    for (const prefix of prefixes) {
      expect(routes.has(prefix)).toBe(false);
    }
  });
});
