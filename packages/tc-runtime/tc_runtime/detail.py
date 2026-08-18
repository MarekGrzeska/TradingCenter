"""What an upstream refused, as a sentence a caller can act on.

One copy of what all three MCP modules carried. They were made identical on 18 August 2026
(iteration 0 of the refactor plan) and differed in exactly two constants afterwards: which
upstream is being named, and which spec is cited. The first is an argument here; the second
is prose and stays with each module.

The list half is what a bad query parameter produces, and it reached a model as the repr of
a list of dicts — `url` to pydantic's error docs and all — until that iteration. The
`isinstance(body, dict)` guard is the other half of the same fix: a JSON body that is not an
object used to raise `AttributeError` from the `.get`, which the `except ValueError` around
it does not catch.
"""

from __future__ import annotations

import httpx


def detail(response: httpx.Response, *, upstream: str) -> str:
    """FastAPI spells a refusal two ways — a `detail` string, or its own list of validation
    objects. Both are the upstream's own words and both travel as a sentence."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or f"{upstream} refused with HTTP {response.status_code}"

    found = body.get("detail") if isinstance(body, dict) else None
    if isinstance(found, str):
        return found
    if isinstance(found, list):
        return "; ".join(one_problem(entry) for entry in found)
    return response.text.strip() or f"{upstream} refused with HTTP {response.status_code}"


def one_problem(entry: object) -> str:
    """One entry of FastAPI's validation list, as a sentence naming the field.

    `msg` on its own is "Field required", which is not something a caller can act on — the
    field's name is in `loc`. The first element of `loc` is FastAPI's own plumbing (`body`,
    `query`, `path`) and says nothing about the request.
    """
    if not isinstance(entry, dict):
        return str(entry)
    message = str(entry.get("msg", entry))
    loc = entry.get("loc")
    if isinstance(loc, list):
        named = [str(part) for part in loc if str(part) not in {"body", "query", "path"}]
        if named:
            return f"{'.'.join(named)}: {message}"
    return message
