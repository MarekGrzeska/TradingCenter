"""What an upstream refused, as a sentence a caller can act on. One copy of what all three MCP modules
carried; the list half used to reach a model as the repr of a list of dicts."""

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
    """One entry of FastAPI's validation list, as a sentence naming the field. `msg` alone is "Field
    required", and the name is in `loc`, whose first element is FastAPI's own plumbing."""
    if not isinstance(entry, dict):
        return str(entry)
    message = str(entry.get("msg", entry))
    loc = entry.get("loc")
    if isinstance(loc, list):
        named = [str(part) for part in loc if str(part) not in {"body", "query", "path"}]
        if named:
            return f"{'.'.join(named)}: {message}"
    return message
