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
        res.end(JSON.stringify({ detail: "capital-gateway is not reachable" }));
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
// capital-gateway has no entry of its own any more: it is not public, and market-data
// proxies the one thing the terminal used to reach it for directly (the instrument
// catalogue) — see gatewaySource.ts and openspec/changes/provision-azure-platform.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const archive = env.ARCHIVE_PROXY_TARGET || "http://localhost:8020";

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
