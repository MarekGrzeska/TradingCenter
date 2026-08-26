"""The one error type this module raises, carrying the status it becomes over HTTP. Converting here
stops an upstream exception from publishing capital.com's shape when things go wrong."""

from __future__ import annotations


class GatewayError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        # 502 by default: the caller's request was fine, the provider's answer was not.
        self.status_code = status_code
