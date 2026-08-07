import { describe, expect, it } from "vitest";
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

  it("resolves all three addresses independently from env", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_GATEWAY_HTTP: "/api",
        VITE_ARCHIVE_HTTP: "/archive",
        VITE_ARCHIVE_WS: "/archive/ws",
      },
      devLoc,
    );
    expect(endpoints).toEqual({
      gatewayHttp: "/api",
      archiveHttp: "/archive",
      archiveWs: "ws://localhost:5173/archive/ws",
    });
  });

  it("resolves a fully split topology — static site, archive and gateway on three hosts", () => {
    const endpoints = resolveEndpoints(
      {
        VITE_GATEWAY_HTTP: "https://gateway.example.com",
        VITE_ARCHIVE_HTTP: "https://archive.example.com",
        VITE_ARCHIVE_WS: "wss://archive.example.com/ws",
      },
      { protocol: "https:", host: "terminal.example.com" },
    );
    expect(endpoints).toEqual({
      gatewayHttp: "https://gateway.example.com",
      archiveHttp: "https://archive.example.com",
      archiveWs: "wss://archive.example.com/ws",
    });
  });

  it("falls back to the dev-proxy prefixes when the env vars are unset, instead of throwing", () => {
    expect(resolveEndpoints({}, devLoc)).toEqual({
      gatewayHttp: "/api",
      archiveHttp: "/archive",
      archiveWs: "ws://localhost:5173/archive/ws",
    });
  });
});
