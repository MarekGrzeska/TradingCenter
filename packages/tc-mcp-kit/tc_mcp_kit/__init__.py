"""What the three MCP modules carried as identical copies, and nothing they didn't.

Split out of `tc-runtime` on 18 August 2026: the two files here need `httpx` and
`starlette` and nothing else, but the three consumers had inherited `tc-runtime`'s whole
dependency tree — `alembic`, `sqlalchemy`, `asyncpg`, `azure-identity`, `aiohttp`,
`fastapi` — for two imports. None of the three modules has a database.
`openspec/changes/packages-replace-the-hand-copies/design.md`, D1, carries the correction
and the measurement that forced it. `README.md` carries the rest.
"""

from . import detail, network_identity, tool_schemas

__all__ = ["detail", "network_identity", "tool_schemas"]
