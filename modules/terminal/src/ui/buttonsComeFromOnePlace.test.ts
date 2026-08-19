import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The same claim `toastsComeFromOnePlace.test.ts` makes, with the same crudeness and for
 * the same reason: this is about where code lives, so no rendering test can hold it.
 *
 * `Button` was written once and then written again fifty times by hand, and the copies
 * did drift — the same primary action carried `border-primary-line` in four places and
 * `border-primary` in three, disabled meant `opacity-40` here, `opacity-50` there and
 * nothing at all somewhere else, and eight quiet buttons had horizontal padding with no
 * vertical padding, so they were a different height from the buttons beside them. None
 * of that fails anything. It is only ever noticed by an operator, one view at a time.
 *
 * So the guard is on the shape rather than on the appearance: a `<button>` that draws
 * itself a rounded border is the terminal's own button, and there is a component for
 * that. Everything else — a tab, a list row, a bare icon — is free.
 */

const SRC = join(process.cwd(), "src");

/** The component allowed to draw a bordered button, relative to `src/`. */
const THE_ONE = join("ui", "Button.tsx");

/**
 * Bordered buttons that are deliberately not `Button`, each named with what it does that
 * no tone here should be stretched to cover. A list is the point: adding to it is a
 * decision somebody makes and can be argued with, which a silent exception is not.
 */
const NOT_THE_TERMINALS_BUTTON: Record<string, string> = {
  [join("agent", "AgentChat.tsx")]:
    "the stop button's alpha border and alpha hover fill, and the send button, whose " +
    "disabled state is a full recolour to quiet rather than the shared opacity",
  [join("teams", "AgentNode.tsx")]:
    "a transparent border that appears only on hover, plus react-flow's nodrag/nopan",
  [join("teams", "TeamRunsStrip.tsx")]:
    "an underlined link wearing a button element, and a chip whose border colour is its " +
    "own hover affordance",
  [join("teams", "DependencyEdge.tsx")]: "a round pill on a react-flow edge, not in a layout",
};

function sourceFiles(dir: string, prefix = ""): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = join(prefix, entry.name);
    if (entry.isDirectory()) return sourceFiles(join(dir, entry.name), relative);
    if (!/\.tsx$/.test(entry.name)) return [];
    if (/\.test\.tsx$/.test(entry.name)) return [];
    return [relative];
  });
}

function contents(relative: string): string {
  return readFileSync(join(SRC, relative), "utf8");
}

/** Every `<button ...>` opening tag in one file. `[^>]*` cannot do this: an
 *  `onClick={() => ...}` attribute contains a `>`. */
function buttonTags(source: string): string[] {
  const tags: string[] = [];
  for (let i = source.indexOf("<button"); i !== -1; i = source.indexOf("<button", i + 1)) {
    let depth = 0;
    for (let j = i; j < source.length; j += 1) {
      const ch = source[j];
      if (ch === "{") depth += 1;
      else if (ch === "}") depth -= 1;
      else if (ch === ">" && depth === 0) {
        tags.push(source.slice(i, j + 1));
        break;
      }
    }
  }
  return tags;
}

describe("every bordered button in the terminal comes from Button", () => {
  it("finds the terminal's own source to read", () => {
    const files = sourceFiles(SRC);
    expect(files.length).toBeGreaterThan(20);
    expect(files).toContain(THE_ONE);
  });

  it("has no view drawing a bordered button by hand", () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => file !== THE_ONE && !(file in NOT_THE_TERMINALS_BUTTON))
      .flatMap((file) =>
        buttonTags(contents(file))
          .filter((tag) => /className="[^"]*rounded border/.test(tag))
          .map(() => file),
      );

    expect(offenders).toEqual([]);
  });

  it("keeps the exception list honest — every file on it still has one", () => {
    // An exception that stopped being true is an exception nobody would notice granting
    // again, which is how a list like this rots into a permanent hole.
    const stale = Object.keys(NOT_THE_TERMINALS_BUTTON).filter(
      (file) => !buttonTags(contents(file)).some((tag) => /className=/.test(tag)),
    );

    expect(stale).toEqual([]);
  });
});
