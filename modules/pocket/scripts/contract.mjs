/**
 * `generate` rewrites the wire types, `check` fails when they are stale. The schema is read from
 * polymarket-data's own Python — a check that needs a running server is a check nobody runs.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, "..");

const SOURCES = [
  {
    name: "social-data",
    moduleDir: resolve(app, "..", "social-data"),
    pythonModule: "social_data.openapi",
    output: join(app, "src", "data", "contract.social.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * Printed from social-data's models by \`python -m social_data.openapi\`. A reading field is present and null
 * where no model has read the post; this file is the only place this app learns that.
 */
`,
  },
  {
    name: "polymarket-data",
    moduleDir: resolve(app, "..", "polymarket-data"),
    pythonModule: "polymarket_data.openapi",
    output: join(app, "src", "data", "contract.polymarket.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * Printed from polymarket-data's models by \`python -m polymarket_data.openapi\`. Every price here is a
 * probability on 0..1, and this file is the only place this app learns that from.
 */
`,
  },
  {
    name: "agent",
    moduleDir: resolve(app, "..", "workbench"),
    pythonModule: "agent.openapi",
    output: join(app, "src", "data", "contract.agent.generated.ts"),
    banner: `/**
 * GENERATED — do not edit. Rewrite it with \`pnpm contract:generate\`.
 *
 * Printed from the workbench's conversation surface by \`python -m agent.openapi\`. The turn's event stream is
 * not in it — OpenAPI does not describe SSE — so \`stream.ts\` stays hand-written against \`agent-chat\`.
 */
`,
  },
];

function schemaJson(source, envDir) {
  try {
    // `--python 3.12`, the floor of `requires-python`, because this document is committed: 3.13 renamed
    // HTTP 422's reason phrase, so regenerating on a newer Python failed `contract:check` with no change.
    return execFileSync("uv", ["run", "--python", "3.12", "python", "-m", source.pythonModule], {
      cwd: source.moduleDir,
      encoding: "utf8",
      // Windows pipes Python's stdout through the ANSI codepage unless told otherwise, turning every em
      // dash into U+FFFD. The throwaway environment keeps 3.12 out of the module's own `.venv`.
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
        `It is printed by \`uv run python -m ${source.pythonModule}\` and needs no database and no\n` +
        `running server — so this failing means the Python environment is missing, not that\n` +
        `something is down.\n`,
    );
    throw err;
  }
}

/** The generated TypeScript for one source's current schema, as a string. */
function generate(source) {
  const scratch = mkdtempSync(join(tmpdir(), "tc-pocket-contract-"));
  try {
    const schema = join(scratch, "openapi.json");
    const emitted = join(scratch, "contract.ts");
    writeFileSync(schema, schemaJson(source, join(scratch, "python-env")));
    // Run by this node, not `npx` or the `.bin` shim: both are `.cmd` on Windows, which node refuses to
    // spawn without a shell since the 2024 argument-injection fix — `spawnSync npx ENOENT`.
    const manifest = fileURLToPath(import.meta.resolve("openapi-typescript/package.json"));
    const cli = join(
      dirname(manifest),
      JSON.parse(readFileSync(manifest, "utf8")).bin["openapi-typescript"],
    );
    execFileSync(process.execPath, [cli, schema, "-o", emitted], {
      cwd: app,
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
    console.error(
      `This file is out of date with its module's schema:\n` +
        stale.map((source) => `  ${source.output}`).join("\n") +
        `\nRun \`pnpm contract:generate\` and commit the result — the generated file is versioned\n` +
        `on purpose, so a contract change shows up as a diff next to the change that caused it.`,
    );
    process.exit(1);
  }
  console.log("The contract is up to date.");
} else {
  console.error("Usage: node scripts/contract.mjs <generate|check>");
  process.exit(2);
}
