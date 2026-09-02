"""The module's OpenAPI document, printed without starting anything — a twin of market-data's, minus the WebSocket
hoisting, since this module has no subscription FastAPI cannot describe: `uv run python -m teams.openapi`."""

from __future__ import annotations

from typing import Any

from tc_runtime.openapi import print_document, require_response_fields

# Built once per process. `require_response_fields` mutates in place and every caller reads the result, so
# handing out two objects that only look alike is a way for one caller's edit to be invisible to the next.
_document: dict[str, Any] | None = None


def document() -> dict[str, Any]:
    """The schema this surface publishes, built in-process from a FastAPI of its own, so the generated TypeScript
    describes *this* surface. `/health` is not here: it belongs to the process, not to either surface."""
    global _document
    if _document is None:
        from fastapi import FastAPI

        from .surface import include

        app = FastAPI(title="TradingCenter · teams", version="0.1.0")
        include(app)
        _document = require_response_fields(app.openapi())
    return _document


def main() -> None:
    print_document(document())


if __name__ == "__main__":
    main()
