import { defineConfig, devices } from "@playwright/test";

/**
 * The terminal from the operator's seat (and the pocket from a phone's), against the end-to-end stack: a workbench on 18030 with its own database on
 * 55442 (`e2e/compose.e2e.yaml`), started before this runs. Vite is started here on its own port and never reused, so a
 * run cannot land on the dev stack's 5173 and 8030.
 */
const NOWHERE = "http://127.0.0.1:9";

export default defineConfig({
  testDir: "e2e/tests",
  // One stack, one database: tests create their own strategies, but runs queue in one worker on the server.
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:15173",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", testIgnore: "**/pocket/**", use: { ...devices["Desktop Chrome"] } },
    // The pocket is the second consumer of the same workbench: it runs after the terminal's tests and only reads what
    // `seed.py` wrote, so nothing here depends on what those tests changed.
    { name: "pocket", testMatch: "**/pocket/**", use: { ...devices["Pixel 7"], baseURL: "http://127.0.0.1:15174" } },
  ],
  webServer: [
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        WORKBENCH_PROXY_TARGET: "http://127.0.0.1:18030",
        ARCHIVE_PROXY_TARGET: "http://127.0.0.1:18030/market",
        GATEWAY_PROXY_TARGET: NOWHERE,
        GATEWAY_PROXY_KEY: "",
        // A terminal .env with Entra configured would send the browser to sign in; unset, the identity is `unconfigured`.
        VITE_ENTRA_CLIENT_ID: "",
        VITE_ENTRA_TENANT_ID: "",
        VITE_ENTRA_SCOPE: "",
      },
    },
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 15174 --strictPort",
      cwd: "../pocket",
      url: "http://127.0.0.1:15174",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        WORKBENCH_PROXY_TARGET: "http://127.0.0.1:18030",
        VITE_ENTRA_CLIENT_ID: "",
        VITE_ENTRA_TENANT_ID: "",
        VITE_ENTRA_SCOPE: "",
      },
    },
  ],
});
