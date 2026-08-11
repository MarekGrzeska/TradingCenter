import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The same claim `dialogsComeFromOnePlace.test.ts` makes, for the same reason and with the
 * same crudeness: this is about where code lives, so no rendering test can hold it.
 *
 * A second toast stack is easy to write — it is a fixed div and a timeout — and it passes
 * every other test here while missing the deduplication that keeps a chart requerying on
 * every candle close from stacking one copy per close, the cap that stops a burst from
 * covering the chart it is talking about, and the `role`/`aria-live` pair a screen reader
 * needs. `alert()` is worse still and is always the shortest path.
 */

const SRC = join(process.cwd(), "src");

/** The component allowed to render toasts, relative to `src/`. */
const THE_ONE = join("ui", "Toaster.tsx");

function sourceFiles(dir: string, prefix = ""): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = join(prefix, entry.name);
    if (entry.isDirectory()) return sourceFiles(join(dir, entry.name), relative);
    if (!/\.tsx?$/.test(entry.name)) return [];
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [relative];
  });
}

function contents(relative: string): string {
  return readFileSync(join(SRC, relative), "utf8");
}

describe("every toast in the terminal comes from Toaster", () => {
  it("finds the terminal's own source to read", () => {
    const files = sourceFiles(SRC);
    expect(files.length).toBeGreaterThan(20);
    expect(files).toContain(THE_ONE);
  });

  it("has no second component announcing a live region of its own", () => {
    const offenders = sourceFiles(SRC).filter(
      (file) => file !== THE_ONE && contents(file).includes("aria-live"),
    );

    expect(offenders).toEqual([]);
  });

  it("never falls back to the browser's own alert()", () => {
    // It cannot be dismissed on the operator's terms, cannot carry a detail worth
    // reading twice, and freezes the chart behind it.
    const offenders = sourceFiles(SRC).filter((file) =>
      /(?:^|[^.\w])(?:window\.)?alert\s*\(/.test(contents(file)),
    );

    expect(offenders).toEqual([]);
  });
});
