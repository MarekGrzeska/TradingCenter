#!/usr/bin/env python3
"""The deterministic half of the system review: size and shape, what landed since a ref, and a
candidate list of the places where database load hides. Only tracked files are read, so `.venv`,
untracked leftovers and nested worktrees never count - a bare `grep -r` here walks site-packages.

    python .claude/skills/system-review/scripts/scan.py --out scan.json \
        [--since <ref>] [--previous <report.html | scan.json>]

Everything under "hotspots" is a candidate, not a finding: each entry still has to be read.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

CODE = (".py", ".ts", ".tsx")
PROSE = (".md", ".html")
# Workbench tests and migration chains are named after their package without the suffix.
ALIASES = {"market": "market_data", "polymarket": "polymarket_data", "social": "social_data"}
LEDGER = re.compile(r'<script type="application/json" id="review-ledger">(.*?)</script>', re.DOTALL)

LOOP = re.compile(r"asyncio\.sleep\(|\bwhile True\b|create_task\(")
DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)")
# Matched per underscore-separated word, or "ticket" reads as a tick.
CADENCE_WORDS = {"interval", "poll", "period", "periods", "cadence", "refresh", "tick", "ticks", "every", "backoff"}
NUMBER = r"([\d_.]+(?:\s*[*/+-]\s*[\d_.]+)*)"
FIELD = re.compile(rf"^\s*(\w+)\s*:\s*(?:int|float)\s*=\s*{NUMBER}\s*(?:#.*)?$")
CONSTANT = re.compile(rf"^(_*[A-Z][A-Z0-9_]*)\s*(?::\s*[\w\[\], |.]+)?=\s*{NUMBER}\s*(?:#.*)?$")
GAUGE = re.compile(r"observable_gauge|create_gauge|class \w*Gauge\b|def \w*gauge\w*|refresh_loop", re.IGNORECASE)
HEALTH = re.compile(
    r"""(?:@\w+\.(?:get|head|api_route)\(|add_api_route\(|Route\()\s*["'](/(?:health|healthz|ping|ready|live)[^"']*)"""
)
POLL = re.compile(r"POLL_MS\s*=|\bpollMs\b|refetchInterval|setInterval\(")

SQL_VERB = re.compile(r"\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|WITH)\b")
SQL_NOUN = re.compile(r"\b(?:FROM|INTO|SET|VALUES|RETURNING)\b")
SQL_LOWER = re.compile(r"\bselect\b[\s\S]*\bfrom\b")
PARAM = re.compile(r"\$\d")
TABLE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+(?:ONLY\s+)?([A-Za-z_][\w.]*)", re.IGNORECASE)
CTE = re.compile(r"(?:\bWITH(?:\s+RECURSIVE)?|,)\s*([A-Za-z_]\w*)\s+AS\s*(?:NOT\s+)?(?:MATERIALIZED\s+)?\(", re.IGNORECASE)
NOT_TABLES = {
    "select", "unnest", "generate_series", "lateral", "values", "only", "set", "jsonb_to_recordset",
    "jsonb_array_elements", "jsonb_each", "json_each", "the", "a", "an", "each", "every", "alembic_version",
}
LOCKING_CLAUSE = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)(?:\s+SKIP\s+LOCKED|\s+NOWAIT)?", re.IGNORECASE)
FLAGS = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "count": r"\bcount\s*\(",
        "distinct": r"\bDISTINCT\b",
        "offset": r"\bOFFSET\b",
        "not_exists": r"\bNOT\s+EXISTS\b",
        "not_in_select": r"\bNOT\s+IN\s*\(\s*SELECT\b",
        "group_by": r"\bGROUP\s+BY\b",
        "min_max": r"\b(?:min|max)\s*\(",
        "sum_avg": r"\b(?:sum|avg)\s*\(",
        "like": r"\bI?LIKE\b",
        "window": r"\bOVER\s*\(",
        "join": r"\bJOIN\b",
        "delete": r"\bDELETE\s+FROM\b",
        "update": r"\bUPDATE\s+[\w.]+\s+SET\b",
        "for_update": r"\bFOR\s+(?:NO\s+KEY\s+)?UPDATE\b",
        "on_conflict": r"\bON\s+CONFLICT\b",
    }.items()
}
# The constructs whose cost can grow with a table rather than with what a statement asks for.
RISKY = {
    "count", "distinct", "offset", "not_exists", "not_in_select", "group_by", "min_max", "sum_avg",
    "like", "window", "no_where", "order_no_limit",
}
CONSTANT_NAME = re.compile(r"^\s*(_*[A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=(?!=)")
QUOTED = re.compile(r"[\"']([^\"']+)[\"']")


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


REPO = Path(_git("rev-parse", "--show-toplevel").strip())


def git(*args: str) -> str:
    return _git(*args, cwd=REPO)


def read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8", errors="replace")


def lines_in(text: str) -> int:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def area_of(path: str) -> str:
    parts = path.split("/")
    if parts[0] == "modules" and len(parts) > 2:
        if parts[1] == "workbench" and len(parts) > 3:
            if parts[2] in ("tests", "migrations"):
                sub = parts[3] if len(parts) > 4 else "workbench"
                return "workbench/" + ALIASES.get(sub, sub)
            return "workbench/" + parts[2]
        return parts[1]
    if parts[0] == "packages" and len(parts) > 2:
        return parts[1]
    return parts[0]


def kind_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "/migrations/" in path:
        return "migration"
    if ".generated." in name:
        return "generated"
    if (
        re.search(r"/(tests?|__tests__)/", path)
        or name.startswith("test_")
        or name == "conftest.py"
        or re.search(r"\.test\.tsx?$", name)
    ):
        return "test"
    return "prod"


# ---------------------------------------------------------------- metrics


def metrics(files: list[str]) -> dict:
    code: dict[str, Counter] = defaultdict(Counter)
    largest: list[tuple[int, str]] = []
    for path in files:
        if path.endswith(CODE):
            count = lines_in(read(path))
            kind = kind_of(path)
            code[area_of(path)][kind] += count
            if kind == "prod":
                largest.append((count, path))
    totals: Counter = Counter()
    for kinds in code.values():
        totals.update(kinds)

    def prose(prefix: str, skip: tuple[str, ...] = ()) -> int:
        return sum(
            lines_in(read(p))
            for p in files
            if p.startswith(prefix) and not p.startswith(skip) and p.endswith(PROSE)
        )

    guide = read("CLAUDE.md") if "CLAUDE.md" in files else ""
    changes = [p.split("/") for p in files if p.startswith("openspec/changes/")]
    revisions = Counter(
        area_of(p) for p in files if "/migrations/" in p and "/versions/" in p and p.endswith(".py")
    )
    return {
        "code_totals": dict(totals),
        "code": {area: dict(kinds) for area, kinds in sorted(code.items())},
        "largest_prod_files": [{"path": p, "lines": n} for n, p in sorted(largest, reverse=True)[:15]],
        "guide": {"chars": len(guide), "approx_tokens": round(len(guide) / 4)},
        "prose_lines": {
            "docs": prose("docs/", ("docs/archive/",)),
            "docs_archive": prose("docs/archive/"),
            "openspec_specs": prose("openspec/specs/"),
            "openspec_active_changes": prose("openspec/changes/", ("openspec/changes/archive/",)),
            "openspec_archive": prose("openspec/changes/archive/"),
            "readmes": sum(lines_in(read(p)) for p in files if p.endswith("README.md")),
        },
        "openspec": {
            "specs": sum(1 for p in files if re.fullmatch(r"openspec/specs/[^/]+/spec\.md", p)),
            "active_changes": sorted({c[2] for c in changes if len(c) > 3 and c[2] != "archive"}),
            "archived_changes": len({c[3] for c in changes if len(c) > 4 and c[2] == "archive"}),
        },
        "settings": settings(files),
        "infra": infra(files),
        "ci": ci(files),
        "migration_revisions": dict(sorted(revisions.items())),
        "claude": claude_dir(),
        "hygiene": hygiene(files),
    }


def settings(files: list[str]) -> dict:
    found = {}
    for path in files:
        if path.endswith(".env.example"):
            live: set[str] = set()
            commented: set[str] = set()
            for line in read(path).splitlines():
                if m := re.match(r"\s*(#\s*)?([A-Z][A-Z0-9_]{2,})\s*=", line):
                    (commented if m.group(1) else live).add(m.group(2))
            found[area_of(path)] = {"set": len(live), "commented_out": len(commented - live)}
    return found


def infra(files: list[str]) -> dict:
    kinds: Counter = Counter()
    module_calls = 0
    for path in files:
        if path.startswith("infra/") and not path.startswith("infra/bootstrap/") and path.endswith(".tf"):
            text = read(path)
            kinds.update(re.findall(r'^\s*resource\s+"(\w+)"', text, re.MULTILINE))
            module_calls += len(re.findall(r'^\s*module\s+"\w+"', text, re.MULTILINE))
    # A block inside infra/modules/ counts once, however many times its module is called.
    return {"resource_blocks": sum(kinds.values()), "module_calls": module_calls, "by_type": dict(kinds.most_common())}


def ci(files: list[str]) -> dict:
    workflows = sorted(
        p.rsplit("/", 1)[-1] for p in files if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))
    )
    jobs: list[str] = []
    if ".github/workflows/checks.yml" in files:
        _, found, body = read(".github/workflows/checks.yml").partition("\njobs:")
        if found:
            jobs = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", body, re.MULTILINE)
    return {"workflows": workflows, "checks_jobs": jobs}


def claude_dir() -> dict:
    base = REPO / ".claude"
    commands = base / "commands"
    return {
        "skills": sorted(p.parent.name for p in (base / "skills").glob("*/SKILL.md")),
        "commands": sorted(p.relative_to(commands).as_posix() for p in commands.rglob("*.md"))
        if commands.is_dir()
        else [],
    }


def hygiene(files: list[str]) -> dict:
    tracked = {p.split("/")[1] for p in files if p.startswith("modules/") and p.count("/") >= 2}
    modules = REPO / "modules"
    leftovers = [
        # The path and whether a .env sits there - never its content.
        {"path": f"modules/{d.name}", "has_env_file": (d / ".env").exists()}
        for d in (sorted(modules.iterdir()) if modules.is_dir() else [])
        if d.is_dir() and d.name not in tracked
    ]

    worktrees = []
    for block in git("worktree", "list", "--porcelain").strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" in fields:
            where = Path(fields["worktree"]).resolve()
            worktrees.append(
                {
                    "path": fields["worktree"],
                    "branch": fields.get("branch", "(detached)").removeprefix("refs/heads/"),
                    "inside_repo": where != REPO.resolve() and REPO.resolve() in where.parents,
                }
            )

    now = datetime.now(timezone.utc)
    ages = {}
    for line in git("for-each-ref", "--format=%(refname:short)%09%(committerdate:iso-strict)", "refs/heads").splitlines():
        name, _, when = line.partition("\t")
        ages[name] = now - datetime.fromisoformat(when)
    merged = subprocess.run(
        ["git", "branch", "--merged", "main", "--format=%(refname:short)"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    return {
        "leftover_module_dirs": leftovers,
        "worktrees": worktrees,
        "branches": len(ages),
        "branches_older_than_30_days": sum(1 for age in ages.values() if age > timedelta(days=30)),
        "branches_merged_into_main": len(set(merged.stdout.split()) - {"main"}) if merged.returncode == 0 else None,
    }


# ---------------------------------------------------------------- hotspots


def unquote(piece: str) -> str:
    match = re.match(r"^[rRbBuUfF]*('''|\"\"\"|'|\")(.*)\1$", piece, re.DOTALL)
    return match.group(2) if match else piece


def literals(text: str) -> Iterator[tuple[int, str]]:
    """(line, content) of every string literal. Adjacent literals are joined as Python joins them, but
    with a newline, so an SQL `--` comment in one piece cannot swallow the next."""
    pending: list | None = None
    fstring: list | None = None
    depth = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            name = tokenize.tok_name[tok.type]
            # From 3.12 an f-string arrives as parts; before that it is one STRING token.
            if name == "FSTRING_START":
                fstring = fstring + [tok.string] if fstring else [tok.start[0], tok.string]
                depth += 1
                continue
            if fstring is not None:
                fstring.append(tok.string)
                if name != "FSTRING_END":
                    continue
                depth -= 1
                if depth:
                    continue
                piece = (fstring[0], "".join(fstring[1:]))
                fstring = None
            elif tok.type == tokenize.STRING:
                piece = (tok.start[0], tok.string)
            elif tok.type in (tokenize.NL, tokenize.COMMENT):
                continue
            else:
                if pending is not None:
                    yield pending[0], "\n".join(pending[1])
                    pending = None
                continue
            if pending is None:
                pending = [piece[0], [unquote(piece[1])]]
            else:
                pending[1].append(unquote(piece[1]))
    except (tokenize.TokenError, SyntaxError):
        pass
    if pending is not None:
        yield pending[0], "\n".join(pending[1])


def is_sql(text: str) -> bool:
    return bool((SQL_VERB.search(text) and SQL_NOUN.search(text)) or (PARAM.search(text) and SQL_LOWER.search(text)))


def sql_entry(path: str, number: int, text: str, lines: list[str], owners: list[str | None]) -> dict:
    ctes = {m.lower() for m in CTE.findall(text)}
    named = {t.split(".")[-1].lower() for t in TABLE.findall(LOCKING_CLAUSE.sub(" ", text))}
    tables = sorted(t for t in named if t not in NOT_TABLES and t not in ctes and not t.startswith("pg_"))
    flags = {name for name, pattern in FLAGS.items() if pattern.search(text)}
    reads = re.search(r"\bSELECT\b", text, re.IGNORECASE) and re.search(r"\bFROM\b", text, re.IGNORECASE)
    if reads and not re.search(r"\b(?:WHERE|LIMIT)\b", text, re.IGNORECASE) and "on_conflict" not in flags:
        flags.add("no_where")
    if re.search(r"\bORDER\s+BY\b", text, re.IGNORECASE) and not re.search(r"\bLIMIT\b", text, re.IGNORECASE):
        flags.add("order_no_limit")
    constant = next(
        (m.group(1) for probe in (number, number - 1) if 1 <= probe <= len(lines) if (m := CONSTANT_NAME.match(lines[probe - 1]))),
        None,
    )
    return {
        "at": f"{path}:{number}",
        "area": area_of(path),
        "name": constant or f"in {owners[number - 1] or '<module>'}()",
        "tables": tables,
        "flags": sorted(flags),
        "head": re.sub(r"\s+", " ", text)[:140],
    }


def hotspots(files: list[str]) -> dict:
    found: dict = {k: [] for k in ("loops", "cadences", "gauges", "health_routes", "screen_polls", "sql")}
    for path in files:
        if kind_of(path) != "prod":
            continue
        if path.endswith(".py"):
            text = read(path)
            lines = text.splitlines()
            owners: list[str | None] = []
            owner = None
            for number, line in enumerate(lines, 1):
                if m := DEF.match(line):
                    owner = m.group(1)
                owners.append(owner)
                where = {"at": f"{path}:{number}", "area": area_of(path)}
                if LOOP.search(line):
                    found["loops"].append({**where, "in": owner, "code": line.strip()[:120]})
                if (m := FIELD.match(line) or CONSTANT.match(line)) and CADENCE_WORDS & set(m.group(1).lower().split("_")):
                    found["cadences"].append({**where, "name": m.group(1), "value": m.group(2)})
                if GAUGE.search(line):
                    found["gauges"].append({**where, "code": line.strip()[:120]})
                if m := HEALTH.search(line):
                    found["health_routes"].append({**where, "route": m.group(1)})
            for number, literal in literals(text):
                if is_sql(literal):
                    found["sql"].append(sql_entry(path, number, literal, lines, owners))
        elif path.endswith((".ts", ".tsx")):
            for number, line in enumerate(read(path).splitlines(), 1):
                if POLL.search(line):
                    found["screen_polls"].append({"at": f"{path}:{number}", "area": area_of(path), "code": line.strip()[:120]})
    found["indexes"] = indexes(files)
    queried = {t for entry in found["sql"] for t in entry["tables"]}
    found["queried_tables_without_known_index"] = sorted(queried - set(found["indexes"]))
    return found


# ---------------------------------------------------------------- indexes from migrations


def balanced(text: str, opening: int) -> str:
    depth = 0
    for at in range(opening, len(text)):
        if text[at] == "(":
            depth += 1
        elif text[at] == ")":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : at]
    return text[opening + 1 :]


def split_top(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for at, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:at])
            start = at + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def sql_columns(text: str) -> list[str]:
    return [p.split()[0] if re.match(r"[A-Za-z_]", p) else p for p in split_top(text)]


def positional_strings(call_body: str) -> list[str]:
    return [m.group(1) for part in split_top(call_body) if (m := QUOTED.fullmatch(part.strip()))]


def without_comments(text: str) -> str:
    """Python comments blanked: a comma or "PRIMARY KEY" in prose splits a column list wrongly."""
    lines = text.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                (row, start), (_, end) = tok.start, tok.end
                lines[row - 1] = lines[row - 1][:start] + " " * (end - start) + lines[row - 1][end:]
    except (tokenize.TokenError, SyntaxError):
        pass
    return "".join(lines)


def before_downgrade(text: str) -> str:
    # A downgrade drops what the upgrade created; reading it would erase every index found.
    end = text.find("def downgrade")
    return text if end == -1 else text[:end]


def indexes(files: list[str]) -> dict:
    entries: dict[str, dict] = {}

    def add(table: str, name: str | None, columns: list[str], unique: bool, kind: str, at: str) -> None:
        table = table.split(".")[-1].lower()
        key = name or f"{table}:{kind}:{','.join(columns)}"
        entries[key] = {"table": table, "name": name, "columns": columns, "unique": unique, "kind": kind, "at": at}

    def drop_table(table: str) -> None:
        table = table.split(".")[-1].lower()
        for key in [k for k, v in entries.items() if v["table"] == table]:
            del entries[key]

    migrations = sorted(p for p in files if "/migrations/" in p and "/versions/" in p and p.endswith(".py"))
    for path in migrations:
        up = before_downgrade(without_comments(read(path)))
        # Raw SQL is read from the literals themselves: one statement is often split across several.
        sql = "\n".join(re.sub(r"--[^\n]*", "", literal) for _, literal in literals(up))
        for m in re.finditer(r"op\.create_table(\()\s*[\"']([\w.]+)[\"']", up):
            table, primary = m.group(2), []
            for part in split_top(balanced(up, m.start(1))):
                if part.startswith("sa.Column("):
                    inner = balanced(part, part.index("("))
                    column = QUOTED.findall(inner)[:1]
                    flat = inner.replace(" ", "")
                    if column and "primary_key=True" in flat:
                        primary += column
                    if column and "unique=True" in flat:
                        add(table, None, column, True, "unique column", path)
                    if column and "index=True" in flat:
                        add(table, None, column, False, "indexed column", path)
                elif part.startswith(("sa.PrimaryKeyConstraint(", "sa.UniqueConstraint(")):
                    inner = balanced(part, part.index("("))
                    named = next((QUOTED.findall(p)[0] for p in split_top(inner) if p.startswith("name=")), None)
                    kind = "primary key" if part.startswith("sa.Primary") else "unique"
                    add(table, named, positional_strings(inner), True, kind, path)
            if primary:
                add(table, None, primary, True, "primary key", path)
        for m in re.finditer(r"op\.create_(index|primary_key|unique_constraint)(\()", up):
            body = balanced(up, m.start(2))
            head, _, rest = body.partition("[")
            names = QUOTED.findall(head)
            if len(names) >= 2:
                columns = QUOTED.findall(rest.partition("]")[0])
                unique = m.group(1) != "index" or "unique=True" in body.replace(" ", "")
                add(names[1], names[0], columns, unique, m.group(1).replace("_", " "), path)
        for m in re.finditer(
            r"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(?:ONLY\s+)?([\w.]+)\s*(?:USING\s+\w+\s*)?(\()",
            sql,
            re.IGNORECASE,
        ):
            add(m.group(3), m.group(2), sql_columns(balanced(sql, m.start(4))), bool(m.group(1)), "index", path)
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)\s*(\()", sql, re.IGNORECASE):
            table, primary = m.group(1), []
            for part in split_top(balanced(sql, m.start(2))):
                constraint = re.match(r"(?:CONSTRAINT\s+(\w+)\s+)?(PRIMARY\s+KEY|UNIQUE)\s*(\()", part, re.IGNORECASE)
                if constraint:
                    kind = "primary key" if constraint.group(2).upper().startswith("PRIMARY") else "unique"
                    add(table, constraint.group(1), sql_columns(balanced(part, constraint.start(3))), True, kind, path)
                elif re.search(r"\bPRIMARY\s+KEY\b", part, re.IGNORECASE):
                    primary.append(part.split()[0])
                elif re.search(r"\bUNIQUE\b", part, re.IGNORECASE) and not part.upper().startswith(("CHECK", "EXCLUDE")):
                    add(table, None, [part.split()[0]], True, "unique column", path)
            if primary:
                add(table, None, primary, True, "primary key", path)
        for m in re.finditer(
            r"ALTER\s+TABLE\s+(?:ONLY\s+)?([\w.]+)\s+ADD\s+(?:CONSTRAINT\s+(\w+)\s+)?(PRIMARY\s+KEY|UNIQUE)\s*(\()", sql, re.IGNORECASE
        ):
            kind = "primary key" if m.group(3).upper().startswith("PRIMARY") else "unique"
            add(m.group(1), m.group(2), sql_columns(balanced(sql, m.start(4))), True, kind, path)
        for m in re.finditer(r"op\.drop_index\(\s*(?:op\.f\(\s*)?[\"']([^\"']+)[\"']", up):
            entries.pop(m.group(1), None)
        for m in re.finditer(r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?([\w.]+)", sql, re.IGNORECASE):
            entries.pop(m.group(1).split(".")[-1], None)
        for m in re.finditer(r"op\.drop_table\(\s*[\"']([\w.]+)[\"']", up):
            drop_table(m.group(1))
        for m in re.finditer(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w.]+)", sql, re.IGNORECASE):
            drop_table(m.group(1))

    by_table: dict[str, list] = defaultdict(list)
    for entry in entries.values():
        by_table[entry["table"]].append({k: v for k, v in entry.items() if k != "table"})
    return dict(sorted(by_table.items()))


# ---------------------------------------------------------------- what landed since a ref


def renamed_to(path: str) -> str:
    """numstat names a move `a/{old => new}/b` or `old => new`; the new side is the file that exists."""
    if " => " not in path:
        return path
    if "{" in path:
        return re.sub(r"\{([^{}]*) => ([^{}]*)\}", lambda m: m.group(2), path).replace("//", "/")
    return path.split(" => ", 1)[1]


def since(ref: str, hot: set[str]) -> dict:
    rows = []
    log = git("log", "--first-parent", "--format=%H%x1f%as%x1f%s%x1f%b%x1e", f"{ref}..HEAD")
    # Rename detection on, so a package moved into the workbench counts its edits, not its size.
    moves = ("-M", "-l5000")
    for record in filter(None, (r.strip() for r in log.split("\x1e"))):
        sha, day, subject, body = (record.split("\x1f") + ["", "", "", ""])[:4]
        if subject.startswith("Merge pull request") and body.strip():
            subject = f"{subject.split(' from ')[0].removeprefix('Merge pull request ')} {body.strip().splitlines()[0]}"
        added = removed = tests = prose_added = 0
        flags: set[str] = set()
        areas: set[str] = set()
        for entry in git("diff", "--numstat", *moves, f"{sha}^1", sha).splitlines():
            plus, minus, path = entry.split("\t", 2)
            path = renamed_to(path)
            if plus == "-" or path.endswith(("uv.lock", "pnpm-lock.yaml")):
                continue
            kind = kind_of(path)
            if path.endswith(CODE):
                areas.add(area_of(path))
            if path.endswith(CODE) and kind == "prod":
                added, removed = added + int(plus), removed + int(minus)
            elif kind == "test":
                tests += int(plus)
            elif path.endswith(PROSE):
                prose_added += int(plus)
            if kind == "migration":
                flags.add("migration")
            if path in hot:
                flags.add("touches_hotspot")
        current = None
        for line in git("diff", "-U0", *moves, f"{sha}^1", sha).splitlines():
            if line.startswith("+++ "):
                current = line[6:] if line.startswith("+++ b/") else None
            elif line.startswith("+") and current and kind_of(current) == "prod":
                added_line = line[1:]
                if current.endswith(".py") and LOOP.search(added_line):
                    flags.add("adds_loop")
                if current.endswith(".py") and SQL_VERB.search(added_line):
                    flags.add("adds_sql")
                if current.endswith((".ts", ".tsx")) and POLL.search(added_line):
                    flags.add("adds_poll")
        rows.append(
            {
                "sha": sha[:7], "date": day, "subject": subject[:120], "prod_added": added,
                "prod_removed": removed, "test_added": tests, "prose_added": prose_added, "flags": sorted(flags),
                "areas": sorted(areas),
            }
        )
    rows.sort(key=lambda r: r["prod_added"] + r["prod_removed"], reverse=True)
    return {
        "ref": ref,
        "commits": len(rows),
        "prod_added": sum(r["prod_added"] for r in rows),
        "prod_removed": sum(r["prod_removed"] for r in rows),
        "test_added": sum(r["test_added"] for r in rows),
        "prose_added": sum(r["prose_added"] for r in rows),
        "largest": rows[:25],
        "flagged": [r for r in rows[25:] if {"adds_loop", "adds_sql", "adds_poll", "migration"} & set(r["flags"])],
    }


def hot_files(found: dict) -> set[str]:
    groups = ("loops", "cadences", "gauges", "health_routes", "screen_polls", "sql")
    return {entry["at"].rsplit(":", 1)[0] for group in groups for entry in found[group]}


# ---------------------------------------------------------------- against the previous review


def flatten(value: object, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            out.update(flatten(inner, f"{prefix}{key}."))
    elif isinstance(value, list):
        out[prefix.rstrip(".")] = len(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        out[prefix.rstrip(".")] = value
    return out


def delta(now: dict, previous: Path) -> dict:
    text = previous.read_text(encoding="utf-8")
    if previous.suffix == ".html":
        match = LEDGER.search(text)
        if not match:
            return {"against": str(previous), "note": "no ledger in this report; compare by reading it"}
        data = json.loads(match.group(1))
    else:
        data = json.loads(text)
    before, after = flatten(data.get("metrics", {})), flatten(now)
    return {
        "against": str(previous),
        "changed": {k: {"before": before[k], "now": after[k]} for k in sorted(after) if k in before and after[k] != before[k]},
        "new": sorted(set(after) - set(before)),
        "gone": sorted(set(before) - set(after)),
    }


# ---------------------------------------------------------------- output


def summary(result: dict, out: Path) -> str:
    m, h = result["metrics"], result["hotspots"]
    totals, prose, hygiene_ = m["code_totals"], m["prose_lines"], m["hygiene"]
    risky = sum(1 for s in h["sql"] if RISKY & set(s["flags"]))
    leftovers, worktrees = hygiene_["leftover_module_dirs"], hygiene_["worktrees"]
    lines = [
        f"scan of {result['commit']}{' (with uncommitted changes)' if result['uncommitted_changes'] else ''} -> {out}",
        (
            f"code lines: prod {totals.get('prod', 0)}, test {totals.get('test', 0)}, "
            f"generated {totals.get('generated', 0)}, migrations {totals.get('migration', 0)}"
        ),
        f"CLAUDE.md: {m['guide']['chars']} chars, ~{m['guide']['approx_tokens']} tokens in every session",
        (
            f"prose lines: docs {prose['docs']} (+{prose['docs_archive']} archived), "
            f"openspec specs {prose['openspec_specs']}, active changes {prose['openspec_active_changes']}, "
            f"archive {prose['openspec_archive']}"
        ),
        (
            f"infra: {m['infra']['resource_blocks']} resource blocks, {m['infra']['module_calls']} module calls; "
            f"CI: {len(m['ci']['workflows'])} workflows, {len(m['ci']['checks_jobs'])} checks jobs"
        ),
        (
            f"hotspots: {len(h['loops'])} loop lines, {len(h['cadences'])} cadence settings, "
            f"{len(h['gauges'])} gauge lines, {len(h['health_routes'])} health routes, "
            f"{len(h['screen_polls'])} screen-poll lines, {len(h['sql'])} SQL statements "
            f"({risky} with constructs that can scale with a table), {len(h['indexes'])} tables with known indexes"
        ),
        (
            f"hygiene: {len(leftovers)} leftover module dirs ({sum(d['has_env_file'] for d in leftovers)} holding a .env), "
            f"{len(worktrees)} worktrees ({sum(w['inside_repo'] for w in worktrees)} inside the repo), "
            f"{hygiene_['branches']} branches ({hygiene_['branches_older_than_30_days']} older than 30 days)"
        ),
    ]
    if "since" in result:
        s = result["since"]
        lines.append(f"since {s['ref']}: {s['commits']} commits, prod +{s['prod_added']}/-{s['prod_removed']}, tests +{s['test_added']}, prose +{s['prose_added']}")
        for row in s["largest"][:8]:
            flags = f" [{', '.join(row['flags'])}]" if row["flags"] else ""
            lines.append(f"  {row['sha']} +{row['prod_added']}/-{row['prod_removed']} {row['subject'][:70]}{flags}")
    if "delta" in result:
        d = result["delta"]
        if "note" in d:
            lines.append(f"previous: {d['note']}")
        else:
            lines.append(f"changed since {d['against']}: {len(d['changed'])} metrics")
            for key, pair in list(d["changed"].items())[:12]:
                lines.append(f"  {key}: {pair['before']} -> {pair['now']}")
    lines.append("candidates only - read the code before calling any of this a finding")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path, help="where to write the JSON")
    parser.add_argument("--since", help="a ref: list what landed on main's first-parent line after it")
    parser.add_argument("--previous", type=Path, help="the previous report (.html with a ledger) or scan (.json)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = [p for p in git("ls-files", "-z").split("\0") if p and (REPO / p).is_file()]
    found = hotspots(files)
    result: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD").strip(),
        "uncommitted_changes": bool(git("status", "--porcelain").strip()),
        "metrics": metrics(files),
        "hotspots": found,
    }
    if args.since:
        result["since"] = since(args.since, hot_files(found))
    if args.previous:
        result["delta"] = delta(result["metrics"], args.previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(summary(result, args.out))


if __name__ == "__main__":
    main()
