"""Who this gateway can write to, and the one tap that makes it possible.

Binding is REST alone and stays there: the link this issues is as good as the destination until it is
used, and a conversation that could hand one out could hand it to the wrong person.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from .. import binding, store
from ..contract import DestinationOut, NewDestinationRequest, Problem, StartLinkOut
from . import deps

router = APIRouter(prefix="/destinations", tags=["destinations"])

EXPIRES_IN_SECONDS = int(binding.NONCE_LIFETIME.total_seconds())


@router.get("", response_model=list[DestinationOut])
async def list_destinations(request: Request) -> list[DestinationOut]:
    """Every destination and how far along it is. One read of the bots, because a name is what a
    caller addresses and the bot behind it is what a response has to name."""
    async with deps.connection(request.app.state.pool) as conn:
        names = {bot.id: bot.username for bot in await store.list_bots(conn)}
        found = await store.list_destinations(conn)
    return [DestinationOut.of(one, names[one.bot_id]) for one in found]


@router.post(
    "",
    response_model=StartLinkOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def offer(request: Request, body: NewDestinationRequest) -> StartLinkOut:
    """Names a destination and hands back the link that will bind it.

    Asking twice is not an error and does not make a second destination: it issues a fresh secret,
    which is what an expired link needs. The destination cannot receive until somebody taps it.
    """
    async with deps.connection(request.app.state.pool) as conn:
        bot = await store.bot_by_username(conn, body.bot)
        if bot is None:
            raise deps.not_found(f"@{body.bot} is not a bot this gateway holds")

        existing = await store.destination_by_name(conn, body.name)
        if existing is not None and existing.bot_id != bot.id:
            # Moving a name to another bot would leave the old conversation bound to it and the new
            # one unable to bind. Deleting the destination is the honest way to say that.
            raise deps.conflict(
                f"{body.name!r} already belongs to another bot. Delete it first — a destination "
                "is a conversation, and it cannot be moved to a bot the person has never met."
            )

        destination, link = await binding.offer(conn, name=body.name, bot=bot)
    return StartLinkOut(
        destination=DestinationOut.of(destination, bot.username),
        start_link=link,
        expires_in_seconds=EXPIRES_IN_SECONDS,
    )


@router.delete(
    "/{name}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": Problem}}
)
async def remove(request: Request, name: str) -> Response:
    """Removes the binding and only the binding — the bot stands, and its other destinations with it."""
    async with deps.connection(request.app.state.pool) as conn:
        if not await store.remove_destination(conn, name):
            raise deps.not_found(f"{name!r} is not a destination this gateway knows")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
