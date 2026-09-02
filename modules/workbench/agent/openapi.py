"""The conversation surface's OpenAPI document, printed without starting anything — the twin of `teams.openapi`,
and the sixth source the terminal generates a contract from: `uv run python -m agent.openapi`. Until P8 this
surface's contract was hand-written in `agentApi.ts`, the one seam CI could not see drift across."""

from __future__ import annotations

from typing import Any

from tc_runtime.openapi import print_document, require_response_fields

# Built once per process, for the reason `teams.openapi` gives: `require_response_fields` mutates in place.
_document: dict[str, Any] | None = None


def document() -> dict[str, Any]:
    """The schema this surface publishes, built in-process from a FastAPI of its own, so the generated TypeScript
    describes *this* surface. The turn's event stream is not here — SSE is not something OpenAPI describes, and
    `stream.ts` stays hand-written against `agent-chat` for that reason."""
    global _document
    if _document is None:
        from fastapi import FastAPI

        from .surface import include

        app = FastAPI(title="TradingCenter · agent", version="0.1.0")
        include(app)
        _document = require_response_fields(app.openapi())
    return _document


def main() -> None:
    print_document(document())


if __name__ == "__main__":
    main()
