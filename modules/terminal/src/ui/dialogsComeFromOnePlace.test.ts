import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * `terminal-dialogs` spec, "Wszystkie dialogi wychodzą z jednego miejsca" — the one
 * requirement of that spec that is a claim about *where code lives* rather than about
 * behaviour, and so the one no rendering test can hold.
 *
 * What it is for: the failure it prevents is nobody's mistake in particular. A fourth
 * confirmation, written from scratch because it was three lines to start with, passes
 * every test in this suite while quietly missing the focus trap, or `Escape`, or the
 * error that has to stay with its decision. Dialogs drift apart one behaviour at a
 * time, and the operator stops knowing what to expect.
 *
 * So this reads the source. Crude on purpose: a component that asks for consent has to
 * come from `ConfirmDialog`, and the two cheap ways around it — announcing `role="dialog"`
 * by hand, or falling back to the browser's own `confirm()` — are named here so that
 * taking either one fails out loud instead of being noticed at review, or not at all.
 */

// Vitest runs from the module root. The first test below checks that this found
// the source at all, so a wrong root fails as itself rather than as an empty walk.
const SRC = join(process.cwd(), "src");

/** The component allowed to be a dialog, relative to `src/`. */
const THE_ONE = join("ui", "ConfirmDialog.tsx");

function sourceFiles(dir: string, prefix = ""): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = join(prefix, entry.name);
    if (entry.isDirectory()) return sourceFiles(join(dir, entry.name), relative);
    if (!/\.tsx?$/.test(entry.name)) return [];
    // Tests say the names of things they assert about, which is not the same as
    // building one.
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [relative];
  });
}

function contents(relative: string): string {
  return readFileSync(join(SRC, relative), "utf8");
}

describe("every dialog in the terminal comes from ConfirmDialog", () => {
  it("finds the terminal's own source to read", () => {
    // Guards the two tests below from passing because the walk found nothing.
    const files = sourceFiles(SRC);
    expect(files.length).toBeGreaterThan(20);
    expect(files).toContain(THE_ONE);
  });

  it("has no second component announcing itself as a dialog", () => {
    const offenders = sourceFiles(SRC).filter(
      (file) => file !== THE_ONE && contents(file).includes('role="dialog"'),
    );

    expect(offenders).toEqual([]);
  });

  it("never falls back to the browser's own confirm()", () => {
    // It cannot say what is at stake, cannot show a failure, and cannot be styled
    // like the rest of the terminal — and it is always the shortest path.
    const offenders = sourceFiles(SRC).filter((file) =>
      /(?:^|[^.\w])(?:window\.)?confirm\s*\(/.test(contents(file)),
    );

    expect(offenders).toEqual([]);
  });
});
