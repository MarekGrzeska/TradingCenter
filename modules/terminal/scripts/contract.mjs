/**
 * The wire types of every module whose contract is generated rather than copied.
 *
 *   node scripts/contract.mjs generate   # rewrite every source's *.generated.ts
 *   node scripts/contract.mjs check      # fail if any of them is stale
 *
 * Why a script and not a one-line pipe: `check` has to produce a message that says what
 * to run, and a pipe that fails prints a diff nobody asked for. It is also the one place
 * that knows each schema comes from that module's own Python, not from a URL —
 * regenerating deliberately needs no running server, because a check that needs one is a
 * check nobody runs, which is how the two copies of market-data's contract drifted apart
 * before this script existed.
 *
 * Generalized from one source to a list of them when `teams` needed the same treatment:
 * agent's own contract stays hand-written (design.md, "Kontrakt terminala pisany ręcznie,
 * bez generatora") precisely because its surface is narrow — the pattern below is for a
 * module whose surface is wide enough that hand-copied types would rot.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const terminal = resolve(here, "..");

const SOURCES = [
  {
    name: "market-data",
    moduleDir: resolve(terminal, "..", "market-data"),
    pythonModule: "market_data.openapi",
    output: join(terminal, "src", "data", "contract.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * The source is market-data's own OpenAPI document, printed straight from its Pydantic
 * models by \`python -m market_data.openapi\`. Everything the terminal reads off that
 * module's wire — including the subscription's Snapshot and CandleChange, which have no
 * HTTP path — is described here, so \`tsc\` is what notices a contract change rather than
 * an operator noticing a blank cell.
 */
`,
  },
  {
    name: "teams",
    moduleDir: resolve(terminal, "..", "workbench"),
    pythonModule: "teams.openapi",
    output: join(terminal, "src", "data", "contract.teams.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * The source is the workbench's teams surface, printed straight from its Pydantic models
 * by \`python -m teams.openapi\`. That surface's own routers and prefixes, not the whole
 * process's: the conversation's contract is hand-written in \`agentApi.ts\` and stays that
 * way. No WebSocket here — unlike market-data's, this schema is exactly what FastAPI
 * already describes on its own.
 */
`,
  },
  {
    name: "polymarket-data",
    moduleDir: resolve(terminal, "..", "polymarket-data"),
    pythonModule: "polymarket_data.openapi",
    output: join(terminal, "src", "data", "contract.polymarket.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * The source is polymarket-data's own OpenAPI document, printed straight from its
 * Pydantic models by \`python -m polymarket_data.openapi\`.
 *
 * **Nothing imports this file yet**, and that is on purpose: the subpage that reads this
 * archive is a change of its own. What it buys before that exists is that
 * \`contract:check\` fails the day the contract moves, so the subpage starts against types
 * that are true rather than against a file born stale.
 *
 * Every price here is a probability on 0..1, never a percentage — the descriptions say
 * so because reading 0.62 as 62 is wrong by two orders of magnitude with no error on
 * the way.
 */
`,
  },
];

function schemaJson(source, envDir) {
  try {
    // `--python 3.12`, the floor of the module's own `requires-python`, because this
    // document is committed and must come out the same everywhere. Left to itself uv
    // takes whatever interpreter satisfies that floor — 3.12 on the CI runner, 3.14 on a
    // developer's machine — and the two disagree: 3.13 renamed HTTP 422's reason phrase
    // from "Unprocessable Entity" to "Unprocessable Content", which FastAPI reads from
    // the stdlib and prints into the schema. Regenerating on a newer Python therefore
    // produced a diff describing no contract change and failed `contract:check` in CI.
    // uv fetches the interpreter if it is missing; the module's tests still run on
    // whatever `requires-python` allows.
    return execFileSync("uv", ["run", "--python", "3.12", "python", "-m", source.pythonModule], {
      cwd: source.moduleDir,
      encoding: "utf8",
      // Windows pipes Python's stdout through the ANSI codepage unless told otherwise,
      // which turned every em dash in a docstring into U+FFFD and made the committed
      // file differ by encoding alone depending on who regenerated it.
      //
      // The pinned interpreter gets its own throwaway environment, so generating the
      // contract does not quietly rebuild the module's own `.venv` on 3.12 underneath
      // whoever is working there.
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
      `Could not read ${source.name}'s OpenAPI document from ${source.moduleDir}.\n` +
        `It is printed by \`uv run python -m ${source.pythonModule}\` and needs no database,\n` +
        `no gateway and no running server — so this failing means the Python environment\n` +
        `is missing, not that something is down.\n`,
    );
    throw err;
  }
}

/** The generated TypeScript for one source's current schema, as a string. */
function generate(source) {
  const scratch = mkdtempSync(join(tmpdir(), "tc-contract-"));
  try {
    const schema = join(scratch, "openapi.json");
    const emitted = join(scratch, "contract.ts");
    writeFileSync(schema, schemaJson(source, join(scratch, "python-env")));
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
    return source.banner + readFileSync(emitted, "utf8");
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

const mode = process.argv[2];

if (mode === "generate") {
  for (const source of SOURCES) {
    writeFileSync(source.output, generate(source));
    console.log(`Wrote ${source.output}`);
  }
} else if (mode === "check") {
  const stale = [];
  for (const source of SOURCES) {
    const fresh = generate(source);
    let committed = null;
    try {
      committed = readFileSync(source.output, "utf8");
    } catch {
      /* missing counts as stale */
    }
    if (committed !== fresh) {
      stale.push(source);
    }
  }
  if (stale.length > 0) {
    const subject = stale.length === 1 ? "This file is out of date with its" : "These files are out of date with their";
    console.error(
      `${subject} module's schema:\n` +
        stale.map((source) => `  ${source.output}`).join("\n") +
        `\nRun \`pnpm contract:generate\` and commit the result — the generated files are\n` +
        `versioned on purpose, so a contract change shows up as a diff next to the change\n` +
        `that caused it.`,
    );
    process.exit(1);
  }
  console.log("Every contract is up to date.");
} else {
  console.error("Usage: node scripts/contract.mjs <generate|check>");
  process.exit(2);
}
