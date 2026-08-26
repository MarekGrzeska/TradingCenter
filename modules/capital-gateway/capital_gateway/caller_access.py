"""Who may reach this module, and which part of it: a module presents the shared
`X-Gateway-Key` and reaches everything, a browser a validated token and the account only."""

from __future__ import annotations

import base64
import binascii
import json

# What the platform authenticator puts on every request it lets through.
PRINCIPAL_HEADER = "x-ms-client-principal"

# The claim naming the application a token was issued to: `azp` in a v2 token, `appid` in a v1
# one. Not `X-MS-CLIENT-PRINCIPAL-ID`, which names the person — deployed, and reverted, 19 Aug 2026.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

# Every path a browser-authenticated caller may reach: the account, and nothing else. Orders,
# the catalogue and the stream are absent on purpose — the screen moves demo money, it does not trade.
BROWSER_PATHS = frozenset(
    {
        "/accounts",
        "/accounts/active",
        "/accounts/top-up",
        "/positions",
        "/working-orders",
    }
)


def calling_application(header_value: str | None) -> str | None:
    """The application a request's token was issued to, or `None` if it cannot be named.
    `None` is a refusal and never a pass."""
    if not header_value:
        return None
    try:
        raw = header_value.encode()
        padded = raw + b"=" * (-len(raw) % 4)
        blob = json.loads(base64.b64decode(padded).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        # A blob that will not decode is not an identity; it is a header to ignore.
        return None

    claims = blob.get("claims") or []
    for name in APPLICATION_CLAIMS:
        for claim in claims:
            if isinstance(claim, dict) and claim.get("typ") == name and claim.get("val"):
                return str(claim["val"]).strip()
    return None


def browser_caller_may_reach(path: str) -> bool:
    """An exact match, not a prefix: `/positions/{id}` closes a position, and a prefix rule
    would hand that to the screen along with the list it is allowed to read."""
    return path in BROWSER_PATHS
