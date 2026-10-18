"""Who this gateway can write to, and the one tap that makes it possible through each bot.

A recipient is a name; reaching it through a bot is a binding of its own, with its own conversation, state and start link.
Binding is REST alone and stays there: the link this issues is as good as the binding until it is used, and a
conversation that could hand one out could hand it to the wrong person.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from .. import binding, store
from ..contract import (
    DestinationOut,
    NewBindingRequest,
    NewRecipientRequest,
    Problem,
    RecipientOut,
    StartLinkOut,
)
from . import deps

router = APIRouter(prefix="/recipients", tags=["recipients"])

EXPIRES_IN_SECONDS = int(binding.NONCE_LIFETIME.total_seconds())


async def _recipients_out(conn) -> list[RecipientOut]:
    """One read of the bots, because a name is what a caller addresses and the bot behind a binding is what a response
    has to name."""
    names = {bot.id: bot.username for bot in await store.list_bots(conn)}
    bindings = await store.list_destinations(conn)
    return [
        RecipientOut.of(
            one.name,
            [DestinationOut.of(found, names[found.bot_id]) for found in bindings if found.name == one.name],
        )
        for one in await store.list_recipients(conn)
    ]


@router.get("", response_model=list[RecipientOut])
async def list_recipients(request: Request) -> list[RecipientOut]:
    async with deps.connection(request.app.state.pool) as conn:
        return await _recipients_out(conn)


@router.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def create(request: Request, body: NewRecipientRequest) -> RecipientOut:
    """Names a recipient. Asking for one that exists is not an error and changes nothing."""
    async with deps.connection(request.app.state.pool) as conn:
        await store.create_recipient(conn, body.name.strip())
        found = [one for one in await _recipients_out(conn) if one.name == body.name.strip()]
    return found[0]


@router.post(
    "/{name}/bots",
    response_model=StartLinkOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": Problem}},
)
async def add_bot(request: Request, name: str, body: NewBindingRequest) -> StartLinkOut:
    """Reaches the recipient through a bot and hands back the link that will bind it.

    Asking twice is not an error and does not make a second binding: it issues a fresh secret, which is what an expired
    link needs. The binding cannot receive until somebody taps it — and a tap on another bot's link does not count.
    """
    async with deps.connection(request.app.state.pool) as conn:
        recipient = await store.recipient_by_name(conn, name)
        if recipient is None:
            raise deps.not_found(f"{name!r} is not a recipient this gateway knows")
        bot = await store.bot_by_username(conn, body.bot.lstrip("@"))
        if bot is None:
            raise deps.not_found(f"@{body.bot.lstrip('@')} is not a bot this gateway holds")

        destination, link = await binding.offer(conn, recipient=recipient, bot=bot)
    return StartLinkOut(
        destination=DestinationOut.of(destination, bot.username),
        start_link=link,
        expires_in_seconds=EXPIRES_IN_SECONDS,
    )


@router.delete(
    "/{name}/bots/{bot}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def remove_binding(request: Request, name: str, bot: str) -> Response:
    """Removes one binding and only that: the bot stands, and so do the recipient's other bindings."""
    async with deps.connection(request.app.state.pool) as conn:
        found = await store.bot_by_username(conn, bot.lstrip("@"))
        if found is None or not await store.remove_destination(conn, name, found.id):
            raise deps.not_found(f"{name!r} is not reached through @{bot.lstrip('@')}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def remove(request: Request, name: str) -> Response:
    """Removes the recipient with every binding of it. The bots stand."""
    async with deps.connection(request.app.state.pool) as conn:
        if not await store.remove_recipient(conn, name):
            raise deps.not_found(f"{name!r} is not a recipient this gateway knows")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
