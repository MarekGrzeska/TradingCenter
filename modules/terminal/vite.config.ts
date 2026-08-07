/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

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
        },
        "/ws": {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
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
