import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { TABS } from "./tabs";

/**
 * The one part of the deployment a test can actually hold: the rule that makes
 * a tab address survive being asked of a server.
 *
 * Every test in this suite drives the router in memory, so none of them can
 * notice that Static Web Apps answers `/grid` with its own 404 page — clicking
 * between tabs never asks a server anything. A reload does, a bookmark does,
 * and so does coming back from sign-in, which is what finally surfaced it.
 */

// Read from disk rather than imported: the file is a deployment artefact that Vite
// copies verbatim, and importing it would prove only that a copy in the bundle
// parses. `process.cwd()` is the module root under vitest.
const config = JSON.parse(
  readFileSync(join(process.cwd(), "public/staticwebapp.config.json"), "utf8"),
) as {
  navigationFallback?: { rewrite?: string; exclude?: string[] };
};

describe("Static Web Apps configuration", () => {
  it("answers an address it has no file for with the app itself", () => {
    expect(config.navigationFallback?.rewrite).toBe("/index.html");
  });

  it("leaves every tab address to the router rather than excluding it", () => {
    // An `exclude` entry is a path the fallback does *not* cover, so a tab
    // caught by one goes back to being a 404 — the failure this file exists to
    // prevent, reintroduced by a pattern that looks harmless.
    const excluded = config.navigationFallback?.exclude ?? [];
    for (const tab of TABS) {
      for (const pattern of excluded) {
        const prefix = pattern.replace(/\*$/, "");
        expect(tab.path.startsWith(prefix)).toBe(false);
      }
    }
  });

  it("keeps a missing bundle a missing bundle", () => {
    // Answering `/assets/*` with `index.html` would hand a browser an HTML page
    // where it asked for JavaScript, and the error it then reports describes a
    // parse failure rather than a file that was never deployed.
    expect(config.navigationFallback?.exclude).toContain("/assets/*");
  });
});
