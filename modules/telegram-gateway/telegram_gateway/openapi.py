"""The module's OpenAPI document, printed without starting anything, so reading it needs no database and no network.

No screen consumes this one — the gateway has no front end, and a notification is its screen. It is
published for the callers that write against the contract by hand, and for the same reason as every
other module's: a document that can only be obtained from a running deployment is not a contract.
"""

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
