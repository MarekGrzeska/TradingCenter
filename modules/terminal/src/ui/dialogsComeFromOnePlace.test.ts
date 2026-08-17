import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * `terminal-dialogs` spec, "Wszystkie dialogi wychodzą z jednego miejsca" — a claim about
 * where code lives rather than about behaviour, so no rendering test can hold it.
 *
 * The failure it prevents is nobody's mistake in particular: a fourth confirmation,
 * written from scratch because it was three lines to start with, passes every other test
 * here while quietly missing the focus trap, or `Escape`, or the error that has to stay
 * with its decision.
 *
 * So this reads the source, crudely on purpose. The two cheap ways around the shared
 * shell — announcing `role="dialog"` by hand, or the browser's own `confirm()` — are named
 * here so taking either fails out loud rather than at review, or not at all.
 *
 * The one place is `ModalShell`, not `ConfirmDialog`: a modal that is a form rather than a
 * question (an agent's settings) has no consent to gather and no work to hold, so it is
 * built on the shell directly. What the spec asks for is that the *behaviours* come from
 * one place, and they do — `ConfirmDialog` is itself now one of the shell's callers.
 */

// Vitest runs from the module root. The first test below checks that this found
// the source at all, so a wrong root fails as itself rather than as an empty walk.
const SRC = join(process.cwd(), "src");

/** The component allowed to be a dialog, relative to `src/`. */
const THE_ONE = join("ui", "ModalShell.tsx");

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

  it("has no second component taking the keyboard for itself", () => {
    // The other half of announcing a dialog, and the half a reader is likelier to copy
    // without the focus trap that has to come with it.
    const offenders = sourceFiles(SRC).filter(
      (file) => file !== THE_ONE && contents(file).includes('aria-modal="true"'),
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
