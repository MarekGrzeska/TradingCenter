import { describe, expect, it } from "vitest";
import { resolveGatewayEndpoints, resolveHttpBase, resolveWsBase } from "./config";

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

describe("resolveGatewayEndpoints", () => {
  it("resolves both addresses independently from env", () => {
    const endpoints = resolveGatewayEndpoints(
      { VITE_GATEWAY_HTTP: "/api", VITE_GATEWAY_WS: "/ws" },
      { protocol: "http:", host: "localhost:5173" },
    );
    expect(endpoints).toEqual({ httpBase: "/api", wsBase: "ws://localhost:5173/ws" });
  });

  it("resolves a fully split-topology configuration (SWA + direct gateway host)", () => {
    const endpoints = resolveGatewayEndpoints(
      {
        VITE_GATEWAY_HTTP: "https://gateway.example.com",
        VITE_GATEWAY_WS: "wss://gateway.example.com/ws",
      },
      { protocol: "https:", host: "terminal.example.com" },
    );
    expect(endpoints).toEqual({
      httpBase: "https://gateway.example.com",
      wsBase: "wss://gateway.example.com/ws",
    });
  });
});
