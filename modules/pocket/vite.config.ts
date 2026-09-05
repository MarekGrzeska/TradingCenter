/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

/**
 * A back end not running is a normal state here, and Vite's stock proxy error handler prints a stack per
 * failed request. This answers with a 502 carrying a readable `detail`, so the app renders its own
 * unreachable state instead of a page of noise.
 */
function quietProxyErrors(label: string, target: string): ProxyOptions["configure"] {
  let lastLoggedAt = 0;
  const LOG_EVERY_MS = 10_000;

  return (proxy) => {
    // Vite registers its own logging handler before calling configure; ours replaces it.
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

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
    const workbench = env.WORKBENCH_PROXY_TARGET || "http://localhost:8030";
  const social = env.SOCIAL_PROXY_TARGET || "http://localhost:8090";

  return {
    plugins: [react()],
    server: {
      // 5174, because the terminal holds 5173 and both are started by `scripts/dev.py`. `--host` is
      // what a phone on the same Wi-Fi needs, and it is left to the command line: binding every
      // interface by default publishes the dev server to the network without anyone asking.
      port: 5174,
      strictPort: true,
      proxy: {
        // No key and no header: polymarket-data takes a token in production and nothing at all in dev,
        // where `REQUIRE_AUTHENTICATED_PRINCIPAL` is off — so there is nothing for this proxy to add.
        "/polymarket-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/polymarket-api/, "/polymarket"),
          configure: quietProxyErrors("workbench", workbench),
        },

        // The post archive, same shape and same reason as the one above.
        "/social-api": {
          target: social,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/social-api/, ""),
          configure: quietProxyErrors("social-data", social),
        },

        // The conversation. Its own address rather than a path under the archive's — a different
        // App Service behind a different gate. No `ws: true`: the turn rides SSE over plain HTTP.
        "/workbench-api": {
          target: workbench,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/workbench-api/, ""),
          configure: quietProxyErrors("workbench", workbench),
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
