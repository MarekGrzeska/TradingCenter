"""The instrument catalogue, proxied from `capital-gateway`.

capital-gateway is not public in production — every caller needs its own caller key, and
a browser is not a place one can be kept (docs/azure-infrastructure-proposal.html,
section 5). The terminal reads the catalogue through this module instead, which already
holds that key for its own upstream calls. Nothing here is reshaped: what the gateway
returns is what a caller of this module gets, unread past the point of forwarding it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..gateway import GatewayInstruments

router = APIRouter()


def instruments(request: Request) -> GatewayInstruments:
    return request.app.state.instruments


@router.get("/instruments", tags=["market-data"])
async def catalogue(
    max_nodes: int | None = Query(None, ge=1, le=5000),
    asset_class: str | None = Query(None),
    gw: GatewayInstruments = Depends(instruments),
):
    return await gw.catalogue(max_nodes, asset_class)


@router.get("/instruments/search", tags=["market-data"])
async def search(q: str = Query(...), gw: GatewayInstruments = Depends(instruments)):
    return await gw.search(q)


@router.get("/asset-classes", tags=["market-data"])
async def asset_classes(gw: GatewayInstruments = Depends(instruments)):
    return await gw.asset_classes()
