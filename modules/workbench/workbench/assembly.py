"""How a package that used to be a module joins this process: its own FastAPI, mounted whole under a prefix.

Mounting rather than including routers keeps everything the package already carries — its `/openapi.json` the
terminal generates a contract from, its `/mcp`, its caller-access middleware and route record — without editing
any of it. The one thing Starlette does not do for a mounted application is run its lifespan, so the host's
lifespan fills the package's `app.state`; this file only places the routes.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.routing import Mount


def mount_package(host: FastAPI, prefix: str, package_app: FastAPI) -> None:
    """Place `package_app` under `prefix`. Refuses a prefix that is not one clean segment and a prefix already
    taken: two packages under one path would answer for each other's routes in mount order, silently."""
    if not prefix.startswith("/") or prefix == "/" or prefix.endswith("/") or "/" in prefix[1:]:
        raise ValueError(f"a package prefix is one segment, like '/polymarket', not {prefix!r}")
    taken = {route.path for route in host.routes if isinstance(route, Mount)}
    if prefix in taken:
        raise ValueError(f"{prefix} is already mounted; a package has one prefix and a prefix has one package")
    host.mount(prefix, package_app, name=prefix.strip("/"))
