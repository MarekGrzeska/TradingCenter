"""Runtime plumbing shared by the modules that have a database or a front door.

Not a framework and not a place for anything that merely *could* be shared. What lands
here has been measured as a hand-maintained copy — at least 70% identical line for line,
with every remaining difference expressible as an argument rather than a branch on which
module is calling (`openspec/changes/archive/…-packages-replace-the-hand-copies/design.md`,
D2). `README.md` carries the measurements and the files that were considered and refused.
"""

from . import auth, db, detail, migrate, network_identity, routers, schema_version

__all__ = [
    "auth",
    "db",
    "detail",
    "migrate",
    "network_identity",
    "routers",
    "schema_version",
]
