/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * A back end not running is a normal state here, and Vite's stock proxy error handler prints a stack per failed
 * request. This answers with a 502 carrying a readable `detail`, so the app renders its own unreachable state.
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

  // The dev-time stand-in for whatever fronts market-data in production. `ARCHIVE_PROXY_TARGET` is server-side, unlike
  // `VITE_ARCHIVE_HTTP`; the gateway's key is added here too, because a browser cannot hold a shared secret.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const archive = env.ARCHIVE_PROXY_TARGET || "http://localhost:8020";
  const workbench = env.WORKBENCH_PROXY_TARGET || "http://localhost:8030";
  const gateway = env.GATEWAY_PROXY_TARGET || "http://localhost:8010";
    const strategy = env.STRATEGY_PROXY_TARGET || "http://localhost:8080";
  const gatewayKey = env.GATEWAY_PROXY_KEY || env.GATEWAY_API_KEY || "";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        // One entry for both roads to the archive, `ws: true` upgrading only what asks. `-api` is not decoration: the
        // prefix was `/archive`, which a tab route also claimed, so anything reaching the server shadowed the tab.
        "/archive-api": {
          target: archive,
          ws: true,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/archive-api/, ""),
          configure: quietProxyErrors("market-data", archive),
        },

        // The workbench's own address, not a path under the archive's — one entry where there were two, since the
        // conversation and the team catalogue are one process. No `ws: true`: both ride `fetch` over plain HTTP.
        "/workbench-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/workbench-api/, ""),
          configure: quietProxyErrors("workbench", workbench),
        },

        // The account. The key is attached here so it stays out of anything the browser downloads — set
        // `GATEWAY_PROXY_KEY` to the same value `capital-gateway`'s `.env` holds as `GATEWAY_API_KEY`.
        "/gateway-api": {
          target: gateway,
          changeOrigin: true,
          headers: gatewayKey ? { "X-Gateway-Key": gatewayKey } : undefined,
          rewrite: (path) => path.replace(/^\/gateway-api/, ""),
          configure: quietProxyErrors("capital-gateway", gateway),
        },

        // The prediction-market archive. No key and no header: a token in production, nothing at all in dev where
        // `REQUIRE_AUTHENTICATED_PRINCIPAL` is off, so there is nothing for this proxy to add.
        "/polymarket-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/polymarket-api/, "/polymarket"),
          configure: quietProxyErrors("workbench", workbench),
        },

        // The post archive, served by the workbench under /social, same shape and same reason as the two above.
        "/social-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/social-api/, "/social"),
          configure: quietProxyErrors("workbench", workbench),
        },

        // The strategy platform, same shape and same reason as the archive above: a token in production, nothing
        // locally.
        "/strategy-api": {
          target: strategy,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/strategy-api/, ""),
          configure: quietProxyErrors("strategy", strategy),
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
