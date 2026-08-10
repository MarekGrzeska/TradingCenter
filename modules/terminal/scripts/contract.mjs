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

function schemaJson(envDir) {
  try {
    // `--python 3.12`, the floor of market-data's own `requires-python`, because this
    // document is committed and must come out the same everywhere. Left to itself uv
    // takes whatever interpreter satisfies that floor — 3.12 on the CI runner, 3.14 on a
    // developer's machine — and the two disagree: 3.13 renamed HTTP 422's reason phrase
    // from "Unprocessable Entity" to "Unprocessable Content", which FastAPI reads from
    // the stdlib and prints into the schema. Regenerating on a newer Python therefore
    // produced a diff describing no contract change and failed `contract:check` in CI.
    // uv fetches the interpreter if it is missing; the module's tests still run on
    // whatever `requires-python` allows.
    return execFileSync("uv", ["run", "--python", "3.12", "python", "-m", "market_data.openapi"], {
      cwd: marketData,
      encoding: "utf8",
      // Windows pipes Python's stdout through the ANSI codepage unless told otherwise,
      // which turned every em dash in a docstring into U+FFFD and made the committed
      // file differ by encoding alone depending on who regenerated it.
      //
      // The pinned interpreter gets its own throwaway environment, so generating the
      // contract does not quietly rebuild `market-data/.venv` on 3.12 underneath whoever
      // is working there.
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
        UV_PROJECT_ENVIRONMENT: envDir,
      },
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
    writeFileSync(schema, schemaJson(join(scratch, "python-env")));
    // The generator's own JS, run by this node — not `npx`, and not the `.bin` shim.
    // Both of those are `.cmd` files on Windows, which node refuses to spawn without a
    // shell (since the 2024 argument-injection fix), so `pnpm contract:generate` failed
    // there with `spawnSync npx ENOENT` while working everywhere else.
    const manifest = fileURLToPath(import.meta.resolve("openapi-typescript/package.json"));
    const cli = join(dirname(manifest), JSON.parse(readFileSync(manifest, "utf8")).bin[
      "openapi-typescript"
    ]);
    execFileSync(process.execPath, [cli, schema, "-o", emitted], {
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
