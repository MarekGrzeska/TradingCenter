"""Runtime plumbing shared by the modules that have a database or a front door.

Not a framework and not a place for anything that merely *could* be shared. What lands
here has been measured as a hand-maintained copy — at least 70% identical line for line,
with every remaining difference expressible as an argument rather than a branch on which
module is calling (`openspec/changes/archive/…-packages-replace-the-hand-copies/design.md`,
D2). `README.md` carries the measurements and the files that were considered and refused.

Was four sub-modules larger until 18 August 2026: `detail` and `network_identity` moved to
`tc-mcp-kit`, because the three MCP modules that took them have no database and were
inheriting this package's whole dependency tree for two imports (`design.md`, D1).
"""

from . import auth, db, migrate, routers, schema_version

__all__ = [
    "auth",
    "db",
    "migrate",
    "routers",
    "schema_version",
]
