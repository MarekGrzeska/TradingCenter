"""The module's OpenAPI document, printed without starting anything, so regenerating needs no database
and no network — which is exactly how two copies of a contract stay together."""

from __future__ import annotations

from typing import Any

from tc_runtime.openapi import print_document, require_response_fields


def document() -> dict[str, Any]:
    """The schema this module publishes, built in-process."""
    from .app import create_app  # local: importing at module level would close a cycle

    return require_response_fields(create_app().openapi())


def main() -> None:
    print_document(document())


if __name__ == "__main__":
    main()
