/**
 * The archive's wire types, generated rather than copied.
 *
 *   node scripts/contract.mjs generate   # rewrite src/data/contract.generated.ts
 *   node scripts/contract.mjs check      # fail if that file is stale
 *
 * Why a script and not a one-line pipe: `check` has to produce a message that says what
 * to run, and a pipe that fails prints a diff nobody asked for. It is also the one place
 * that knows the schema comes from `market-data`'s Python, not from a URL — regenerating
 * deliberately needs no running server, because a check that needs one is a check nobody
 * runs, which is how the two copies of this contract drifted apart before it existed.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const terminal = resolve(here, "..");
const marketData = resolve(terminal, "..", "market-data");
const output = join(terminal, "src", "data", "contract.generated.ts");

const BANNER = `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * The source is market-data's own OpenAPI document, printed straight from its Pydantic
 * models by \`python -m market_data.openapi\`. Everything the terminal reads off that
 * module's wire — including the subscription's Snapshot and CandleChange, which have no
 * HTTP path — is described here, so \`tsc\` is what notices a contract change rather than
 * an operator noticing a blank cell.
 */
`;

function schemaJson() {
  try {
    return execFileSync("uv", ["run", "python", "-m", "market_data.openapi"], {
      cwd: marketData,
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch (err) {
    console.error(
      `Could not read market-data's OpenAPI document from ${marketData}.\n` +
        `It is printed by \`uv run python -m market_data.openapi\` and needs no database,\n` +
        `no gateway and no running server — so this failing means the Python environment\n` +
        `is missing, not that something is down.\n`,
    );
    throw err;
  }
}

/** The generated TypeScript for the current schema, as a string. */
function generate() {
  const scratch = mkdtempSync(join(tmpdir(), "tc-contract-"));
  try {
    const schema = join(scratch, "openapi.json");
    const emitted = join(scratch, "contract.ts");
    writeFileSync(schema, schemaJson());
    execFileSync("npx", ["openapi-typescript", schema, "-o", emitted], {
      cwd: terminal,
      encoding: "utf8",
      stdio: ["ignore", "ignore", "inherit"],
    });
    return BANNER + readFileSync(emitted, "utf8");
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

const mode = process.argv[2];

if (mode === "generate") {
  writeFileSync(output, generate());
  console.log(`Wrote ${output}`);
} else if (mode === "check") {
  const fresh = generate();
  let committed = null;
  try {
    committed = readFileSync(output, "utf8");
  } catch {
    /* missing counts as stale */
  }
  if (committed !== fresh) {
    console.error(
      `src/data/contract.generated.ts does not match market-data's schema.\n` +
        `Run \`pnpm contract:generate\` and commit the result — the generated file is\n` +
        `versioned on purpose, so a contract change shows up as a diff next to the change\n` +
        `that caused it.`,
    );
    process.exit(1);
  }
  console.log("Contract is up to date.");
} else {
  console.error("Usage: node scripts/contract.mjs <generate|check>");
  process.exit(2);
}
