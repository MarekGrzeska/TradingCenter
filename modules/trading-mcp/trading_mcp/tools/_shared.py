"""Helpers every tool submodule needs: the annotation every write and every read
carries, and the two seams that turn a `GatewayClient` outcome into what a tool
answers.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel

from ..client import GatewayClient
from ..errors import GatewayRefused, GatewayUnavailable, NotDemoEnvironment, ToolRefusal

# Applied to every read tool — a structural claim an MCP client can act on without
# reading this module's source (specs/trading-mcp-tools, "Narzędzie zapisujące jest
# oznaczone jako zmieniające stan").
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# Applied to every tool that can change the account. `idempotentHint=False` because
# none of the four repeat safely: a second `place_order` is a second position, a
# second `close_position` on an already-closed id is refused rather than a no-op.
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


class OrderResultOut(BaseModel):
    """What every write tool answers with on anything but a refusal.

    `outcome="unsettled"` is `capital-gateway`'s own PENDING, carried through rather
    than resolved — the gateway already exhausted its own confirm-poll budget before
    answering this way, so retrying the read here would only repeat that wait
    (specs/trading-mcp-execution, "Wynik zlecenia jest rozliczony albo nazwany jako
    nierozliczony"). `status="REJECTED"` never reaches this model — see `_write`.
    """

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
        # `is_access_failure` and not `status_code >= 500`: a 401 here is this module's
        # credential being rejected, and answering "refused" would let a read that never
        # happened read as an answer about the account (`errors.py` holds the whole
        # list and the reasoning).
        if err.is_access_failure:
            raise ToolRefusal(
                f"access failure: capital-gateway answered {err.status_code} "
                f"({err.detail}). Nothing was read — this is a failure on this module's "
                "side, not an answer about the account."
            ) from err
        raise ToolRefusal(
            f"refused: capital-gateway answered {err.status_code} ({err.detail})."
        ) from err


async def _write(
    gateway: GatewayClient, method: str, path: str, json: dict | None = None
) -> OrderResultOut:
    """Confirm the account is a demo one, send the write, and translate what came back.

    See `trading-mcp-execution` and `trading-mcp-tools`'s "Odmowa narzędzia jest
    odróżnialna od awarii dostępu" for the three outcomes this collapses into two: a
    `ToolRefusal` either names an access failure whose effect on the account is unknown,
    or a refusal that never touched it — a provider REJECTED, or a `4xx`
    capital-gateway's own validation stopped before calling the provider at all. Which
    status is which is `GatewayRefused.is_access_failure`, not a comparison written
    here: a `5xx` can happen after the provider already saw the request, and a `401`
    means nobody looked at it at all, and only one of those two is the caller's to fix.

    **The demo check belongs inside this seam, not in front of it.** Every write tool
    used to call `ensure_demo_environment()` itself, one line above `_write`, which left
    its `GatewayError`s as the only ones in the module reaching a caller unwrapped —
    without the wording every other failure here carries, and looking like a refusal of
    the order rather than a check that never got to ask. Its failures are their own
    sentence: at that point **nothing has been sent**, which is the one thing an agent
    needs to know before deciding what to do next.
    """
    try:
        await gateway.ensure_demo_environment()
    except NotDemoEnvironment as err:
        raise ToolRefusal(
            f"refused: {err} Nothing was sent — this module places orders on the demo "
            "account and on no other."
        ) from err
    except GatewayUnavailable as err:
        raise ToolRefusal(
            f"access failure: could not reach capital-gateway to confirm the account is "
            f"a demo one ({err}). Nothing was sent."
        ) from err
    except GatewayRefused as err:
        raise ToolRefusal(
            f"access failure: capital-gateway answered {err.status_code} ({err.detail}) "
            "when asked to confirm the account is a demo one. Nothing was sent."
        ) from err

    try:
        payload = await gateway.write(method, path, json=json)
    except GatewayUnavailable as err:
        raise ToolRefusal(
            f"access failure: could not reach capital-gateway ({err}). The effect of "
            "this request on the account is unknown — read positions or working "
            "orders before trying again; do not repeat this call."
        ) from err
    except GatewayRefused as err:
        if err.is_access_failure:
            raise ToolRefusal(
                f"access failure: capital-gateway answered {err.status_code} "
                f"({err.detail}). The effect of this request on the account is "
                "unknown — read positions or working orders before trying again; do "
                "not repeat this call."
            ) from err
        raise ToolRefusal(f"refused: capital-gateway rejected the request — {err.detail}") from err

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
