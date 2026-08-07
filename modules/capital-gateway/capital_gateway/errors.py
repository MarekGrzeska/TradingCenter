"""The one error type this module raises, carrying the status it becomes over HTTP.

Every provider failure is converted here rather than propagating an httpx error: a
caller of this module deals in its contract, and an upstream exception leaking through
would publish capital.com's shape at exactly the moment things go wrong.
"""

from __future__ import annotations


class GatewayError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        # 502 by default: the caller's request was fine, the provider's answer was not.
        self.status_code = status_code
