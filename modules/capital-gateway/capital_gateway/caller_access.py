"""Who may reach this module, and which part of it.

This module has two kinds of caller and they cannot present the same credential.

**A module** — `market-data`, `trading-mcp` — calls over the network with the shared
`X-Gateway-Key`, and reaches everything. That is the arrangement `capital-access-control`
has always described, and nothing here changes it.

**A browser** — the terminal's Accounts screen — cannot carry that key: a secret in
downloaded code is a published secret. What it carries instead is a token, validated by the
platform in front of this app, whose claims name the application it was issued to. This file
is what turns that name into an answer, and it answers narrowly: the account, and nothing
else. A caller who came through the platform's door is *not* thereby allowed to place an
order — the platform authorizes an application, not a route.

**The record is a list of what is allowed, so anything new is refused by default.** A route
added next month is out of reach of a browser on the day it is written, and stays that way
until somebody adds it here on purpose. That default is worth more than any single entry in
the list.

`market_data/caller_access.py` is this file's older, larger twin, and the claim-reading below
is deliberately a second copy of ~20 lines rather than a shared package: the one package that
could hold it (`tc-mcp-kit`) is about speaking MCP, which this module does not do, and two
short copies are not what the sharing rule in `docs/architecture.md` is for.
"""

from __future__ import annotations

import base64
import binascii
import json

# What the platform authenticator puts on every request it lets through.
PRINCIPAL_HEADER = "x-ms-client-principal"

# The claim naming the application a token was issued to: `azp` in a v2 token, `appid` in a
# v1 one, and Easy Auth passes some claim types through in their long URI form.
#
# Not `X-MS-CLIENT-PRINCIPAL-ID`, which for a delegated token names the **person** at the
# keyboard rather than the application. `market-data` deployed the opposite assumption on
# 19 August 2026 and refused every request the terminal made until the image went back.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

# Every path a browser-authenticated caller may reach. The account, in other words: what it
# holds, what is open on it, which one is active and how much money is on it.
#
# What is deliberately absent is the rest of this module — placing an order, closing a
# position, moving stops, cancelling a working order, the instrument catalogue and the
# stream. The screen shows a balance and moves demo money; it does not trade.
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

    `None` is a refusal and never a pass: a request whose calling application cannot be read
    is exactly the request this record has nothing to say about.
    """
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
    """Whether a browser-authenticated caller has business at this path.

    An exact match, not a prefix: `/positions/{id}` closes a position, and a prefix rule
    would hand that to the screen along with the list it is allowed to read.
    """
    return path in BROWSER_PATHS
