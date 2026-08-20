"""The instrument catalogue, proxied from `capital-gateway`.

Every caller of capital-gateway needs its caller key, and a browser is not a place one can be
kept (docs/azure-infrastructure-proposal.html, section 5). That, and not a closed network, is
what routes the catalogue through here: the gateway's address answers anybody who knows it —
measured 20 August 2026, when the address list this repo believed in turned out never to have
existed — and the key is the whole of its door. The terminal reads the catalogue through this module instead, which already
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
