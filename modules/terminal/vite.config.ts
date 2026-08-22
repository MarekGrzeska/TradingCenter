/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * A back end not running is a normal state here — the terminal has no offline
 * mode and both services are started separately. Vite's stock proxy error
 * handler prints a multi-line stack for every failed request, so a grid of six
 * charts retrying on a backoff buries the console in identical AggregateErrors
 * that say nothing the first one didn't.
 *
 * This replaces that handler with one throttled line, and answers the request
 * with a 502 carrying a readable `detail` so the app renders its own
 * "source unreachable" state rather than a transport failure.
 */
function quietProxyErrors(label: string, target: string): ProxyOptions["configure"] {
  let lastLoggedAt = 0;
  const LOG_EVERY_MS = 10_000;

  return (proxy) => {
    // Vite registers its own logging handler before calling configure; ours is
    // meant to replace it, not pile on.
    proxy.removeAllListeners("error");

    proxy.on("error", (err: NodeJS.ErrnoException, _req, res) => {
      const now = Date.now();
      if (now - lastLoggedAt > LOG_EVERY_MS) {
        lastLoggedAt = now;
        const reason =
          err.code === "ECONNREFUSED"
            ? `nothing listening on ${target}`
            : `${err.code ?? "error"}: ${err.message}`;
        console.warn(
          `[proxy:${label}] ${reason}. Start it — see modules/${label}/README.md. ` +
            `Further errors are silenced for ${LOG_EVERY_MS / 1000}s.`,
        );
      }

      // `res` is a ServerResponse for HTTP and a Socket for a WebSocket upgrade.
      if ("writeHead" in res) {
        if (!res.headersSent) {
          res.writeHead(502, { "Content-Type": "application/json" });
        }
        res.end(JSON.stringify({ detail: `${label} is not reachable` }));
      } else {
        res.destroy();
      }
    });
  };
}

// The dev-time stand-in for whatever sits in front of market-data in production (Front
// Door, Application Gateway, ...). `ARCHIVE_PROXY_TARGET` is server-side and read only
// here, distinct from `VITE_ARCHIVE_HTTP` / `VITE_ARCHIVE_WS`, which are client-side and
// point at the prefix below in dev — see design.md.
//
// capital-gateway has an entry again, and it carries the caller key on the server side.
// The gateway demands a credential from every caller, and a browser cannot hold a shared
// secret — in production it presents a token instead, which the platform validates before
// the request arrives. In dev there is no platform, so the dev server is what adds the
// key: `GATEWAY_PROXY_KEY` is server-side and never reaches the bundle
// (openspec/changes/accounts-screen-opens-the-gateway/design.md, D5).
//
// The instrument catalogue still comes through market-data, unchanged — this entry is the
// account, not a second road to the market (see gatewaySource.ts).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const archive = env.ARCHIVE_PROXY_TARGET || "http://localhost:8020";
  const workbench = env.WORKBENCH_PROXY_TARGET || "http://localhost:8030";
  const gateway = env.GATEWAY_PROXY_TARGET || "http://localhost:8010";
  const polymarket = env.POLYMARKET_PROXY_TARGET || "http://localhost:8070";
  const gatewayKey = env.GATEWAY_PROXY_KEY || env.GATEWAY_API_KEY || "";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        // One entry for both roads to the archive: `/archive-api/...` is its
        // HTTP contract and `/archive-api/ws/candles` its subscription, and
        // `ws: true` upgrades only the request that asks to be upgraded.
        //
        // `-api` is not decoration. The prefix was `/archive`, which back then
        // was also a tab's route — so a proxy claiming that prefix shadowed the
        // tab for anything that reaches the server: a reload, a bookmark, the
        // link `scripts/dev.sh` prints. Clicking through still worked, because
        // the router never asks, which is exactly why it survived the test
        // suite. Whatever fronts market-data in production would shadow a tab
        // the same way, so the fix is the prefix, not the dev server.
        "/archive-api": {
          target: archive,
          ws: true,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/archive-api/, ""),
          configure: quietProxyErrors("market-data", archive),
        },

        // The workbench's own address, not a path under the archive's — it is an
        // independent module on 8030. One entry where there were two: the conversation and
        // the team catalogue are one process, so `/agent-api` and `/teams-api` became this.
        //
        // No `ws: true`: a turn and a run's progress both ride `fetch` + `ReadableStream`
        // over plain HTTP, never a WebSocket upgrade.
        "/workbench-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/workbench-api/, ""),
          configure: quietProxyErrors("workbench", workbench),
        },

        // The account. The key is attached here, in the dev server, so it stays out of
        // anything the browser downloads — set `GATEWAY_PROXY_KEY` to the same value
        // `capital-gateway`'s own `.env` holds as `GATEWAY_API_KEY`.
        "/gateway-api": {
          target: gateway,
          changeOrigin: true,
          headers: gatewayKey ? { "X-Gateway-Key": gatewayKey } : undefined,
          rewrite: (path) => path.replace(/^\/gateway-api/, ""),
          configure: quietProxyErrors("capital-gateway", gateway),
        },

        // The prediction-market archive. No key and no header: it wants a token in
        // production and nothing at all in dev, where `REQUIRE_AUTHENTICATED_PRINCIPAL`
        // is off — so unlike the gateway above there is nothing for this proxy to add.
        "/polymarket-api": {
          target: polymarket,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/polymarket-api/, ""),
          configure: quietProxyErrors("polymarket-data", polymarket),
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: true,
    },
  };
});
