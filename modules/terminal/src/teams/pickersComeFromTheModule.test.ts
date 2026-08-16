import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * `terminal-teams`, "terminal MUST NOT nieść własnej listy jednych ani drugich", and
 * specs/teams-models, "wybierak powstaje bez ani jednego identyfikatora modelu wpisanego
 * w kod terminala" — claims about what the source does *not* contain, which no rendering
 * test can hold. `TeamsView.test.tsx` proves the pickers render what the module answered;
 * this proves there is no second list to fall back to.
 *
 * The failure it prevents is the cheap one: a model added to the module's configuration,
 * a `<option value="gpt-…">` added here to match, and from then on the two lists agree
 * only as long as somebody remembers both. Crude on purpose, like
 * `dialogsComeFromOnePlace.test.ts` — the two ways this gets written by hand are named
 * below so taking either fails out loud.
 */

const TEAMS = join(process.cwd(), "src", "teams");

/** What a model id looks like on every provider's pricing page — and what
 *  `ModelCatalogueEntry.id` in the module's own configuration is set from. */
const MODEL_ID = /\b(gpt|claude|gemini|llama|mistral|o\d)[-.][\w.-]+/i;

/** market-mcp announces snake_case names like these; a definition points at one by name
 *  and this terminal only ever learns them from `GET /tools`. */
const TOOL_NAME = /\b(get|list|read)_[a-z_]+\b/;

function sourceFiles(dir: string, prefix = ""): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = join(prefix, entry.name);
    if (entry.isDirectory()) return sourceFiles(join(dir, entry.name), relative);
    if (!/\.tsx?$/.test(entry.name)) return [];
    // A test names the things it asserts about; that is not the same as shipping a list.
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [relative];
  });
}

function contents(relative: string): string {
  return readFileSync(join(TEAMS, relative), "utf8");
}

/** Fields of the module's own wire that read like a tool name to the pattern above.
 *  `read_only` is a property of every announced tool and is exactly what makes the picker
 *  able to mark the ones that move the account — the opposite of a tool list written down
 *  here, so it is taken out before the check rather than the check being loosened. */
function withoutWireFields(relative: string): string {
  return contents(relative).replace(/\bread_only\b/g, "");
}

describe("the model and tool pickers carry no list of their own", () => {
  it("finds the tab's own source to read", () => {
    const files = sourceFiles(TEAMS);
    expect(files.length).toBeGreaterThan(5);
    expect(files).toContain("teamsApi.ts");
  });

  it("names no model", () => {
    const offenders = sourceFiles(TEAMS).filter((file) => MODEL_ID.test(contents(file)));
    expect(offenders).toEqual([]);
  });

  it("names no tool", () => {
    const offenders = sourceFiles(TEAMS).filter((file) => TOOL_NAME.test(withoutWireFields(file)));
    expect(offenders).toEqual([]);
  });
});
