"""The module's OpenAPI document, printed without starting anything, so regenerating needs no database and no network.
Both front ends generate their wire types from it, and `contract:check` fails the day it moves."""

from __future__ import annotations

from typing import Any

from tc_runtime.openapi import print_document, require_response_fields


def document() -> dict[str, Any]:
    """The schema this module publishes, built in-process."""
    from .app import app  # local: importing at module level would close a cycle

    return require_response_fields(app.openapi())


def main() -> None:
    print_document(document())


if __name__ == "__main__":
    main()
