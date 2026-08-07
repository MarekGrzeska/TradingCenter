/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * "capital-gateway is not running" is a normal state here — the terminal's
 * default source is the offline mock, and the gateway is opt-in. Vite's stock
 * proxy error handler prints a multi-line stack for every failed request, so a
 * grid of six charts retrying on a backoff buries the console in identical
 * AggregateErrors that say nothing the first one didn't.
 *
 * This replaces that handler with one throttled line, and answers the request
 * with a 502 carrying a readable `detail` so the app renders its own
 * "source unreachable" state rather than a transport failure.
 */
function quietGatewayProxyErrors(label: string, target: string): ProxyOptions["configure"] {
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
            ? `no capital-gateway on ${target}`
            : `${err.code ?? "error"}: ${err.message}`;
        console.warn(
          `[proxy:${label}] ${reason}. Start it with ./scripts/dev.ps1 -WithGateway, ` +
            `or switch Source to "mock" in the terminal. Further errors are silenced ` +
            `for ${LOG_EVERY_MS / 1000}s.`,
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

// The dev-time stand-in for whatever sits in front of capital-gateway in production
// (Front Door, Application Gateway, ...). `GATEWAY_PROXY_TARGET` is a server-side
// variable read here, distinct from `VITE_GATEWAY_HTTP`/`VITE_GATEWAY_WS`, which are
// client-side and point at `/api`/`/ws` in dev — see design.md.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.GATEWAY_PROXY_TARGET || "http://localhost:8010";
  const wsTarget = target.replace(/^http/, "ws");

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          configure: quietGatewayProxyErrors("api", target),
        },
        "/ws": {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
          configure: quietGatewayProxyErrors("ws", target),
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
