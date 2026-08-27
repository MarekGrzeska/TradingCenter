"""Helpers every tool submodule needs: the annotation every write and every read carries, and the two
seams that turn a `GatewayClient` outcome into what a tool answers."""

from __future__ import annotations

from typing import Any, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel

from ..client import GatewayClient
from ..errors import GatewayRefused, GatewayUnavailable, ToolRefusal

# Applied to every read tool — a structural claim an MCP client can act on without reading this source.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# Applied to every tool that can change the account. `idempotentHint=False` because none of the four
# repeat safely: a second `place_order` is a second position.
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


class OrderResultOut(BaseModel):
    """What every write tool answers with on anything but a refusal. `outcome="unsettled"` is the
    gateway's own PENDING, carried through rather than resolved — it already spent its poll budget."""

    outcome: Literal["settled", "unsettled"]
    status: str
    id: str | None = None
    reference: str | None = None
    symbol: str | None = None
    direction: str | None = None
    size: float | None = None
    level: float | None = None


async def _read(gateway: GatewayClient, path: str) -> Any:
    try:
        return await gateway.get(path)
    except GatewayUnavailable as err:
        raise ToolRefusal(
            f"access failure: could not reach capital-gateway ({err}). This is a "
            "failure on this module's side, not an answer about the account."
        ) from err
    except GatewayRefused as err:
        # `is_access_failure` and not `status_code >= 500`: a 401 here is this module's credential
        # being rejected, and answering "refused" would let a read that never happened read as one.
        if err.is_access_failure:
            raise ToolRefusal(
                f"access failure: capital-gateway answered {err.status_code} "
                f"({err.detail}). Nothing was read — this is a failure on this module's "
                "side, not an answer about the account."
            ) from err
        raise ToolRefusal(
            f"refused: capital-gateway answered {err.status_code} ({err.detail})."
        ) from err


async def _send_change(
    gateway: GatewayClient,
    method: str,
    path: str,
    json: dict | None = None,
    *,
    read_back: str,
) -> Any:
    """The error translation every write shares, without any reading of what came back. `read_back` is
    what the model should look at before trying again, and it differs by what was being changed."""
    try:
        return await gateway.write(method, path, json=json)
    except GatewayUnavailable as err:
        raise ToolRefusal(
            f"access failure: could not reach capital-gateway ({err}). The effect of "
            f"this request on the account is unknown — {read_back} before trying again; "
            "do not repeat this call."
        ) from err
    except GatewayRefused as err:
        if err.is_access_failure:
            raise ToolRefusal(
                f"access failure: capital-gateway answered {err.status_code} "
                f"({err.detail}). The effect of this request on the account is "
                f"unknown — {read_back} before trying again; do not repeat this call."
            ) from err
        raise ToolRefusal(f"refused: capital-gateway rejected the request — {err.detail}") from err


async def _write(
    gateway: GatewayClient, method: str, path: str, json: dict | None = None
) -> OrderResultOut:
    """Send the write, and translate what came back into two outcomes: an access failure whose effect
    is unknown, or a refusal that never touched the account. The demo check is not here — it ran once."""
    payload = await _send_change(
        gateway,
        method,
        path,
        json=json,
        read_back="read positions or working orders",
    )

    status: str = payload["status"]
    if status == "REJECTED":
        raise ToolRefusal(f"refused: the provider rejected the order — {payload.get('reason')}")
    outcome: Literal["settled", "unsettled"] = "unsettled" if status == "PENDING" else "settled"
    return OrderResultOut(
        outcome=outcome,
        status=status,
        id=payload.get("id"),
        reference=payload.get("reference"),
        symbol=payload.get("symbol"),
        direction=payload.get("direction"),
        size=payload.get("size"),
        level=payload.get("level"),
    )
