"""The bots this gateway may speak as. Every route here is REST and stays REST — a bot outlives the
conversation that asked for it, so `telegram-gateway-tools` keeps the whole of this off that surface.

Two ways in, and they are not two flavours of one: adopting a token the operator pasted always works,
creating one needs the account session that `/state` reports on.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from .. import bots, creator, store
from ..contract import AdoptBotRequest, BotOut, NewBotRequest, Problem
from ..errors import CreatingBotsUnavailable, GatewayError
from . import deps

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_model=list[BotOut])
async def list_bots(request: Request) -> list[BotOut]:
    """Every bot, without a token among them — `BotOut` has nowhere to put one."""
    async with deps.connection(request.app.state.pool) as conn:
        return [BotOut.of(bot) for bot in await store.list_bots(conn)]


@router.post(
    "/adopted",
    response_model=BotOut,
    status_code=status.HTTP_201_CREATED,
    responses={502: {"model": Problem}},
)
async def adopt(request: Request, body: AdoptBotRequest) -> BotOut:
    """A bot that already exists, added by its token. Telegram is asked who it belongs to.

    The response is the bot as every read publishes it: the token went to the database and does not
    come back out, including on the request that carried it in.
    """
    async with deps.connection(request.app.state.pool) as conn:
        try:
            adopted = await bots.adopt(conn, request.app.state.telegram, token=body.token)
        except GatewayError as err:
            raise deps.refusal(err) from err
    # Now rather than at the next restart: adopting a bot is usually followed by binding a
    # destination to it, and nothing binds while nobody is polling.
    request.app.state.watcher.watch(adopted)
    return BotOut.of(adopted)


@router.post(
    "/created",
    response_model=BotOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": Problem}, 422: {"model": Problem}, 501: {"model": Problem}, 502: {"model": Problem}},
)
async def create(request: Request, body: NewBotRequest) -> BotOut:
    """A new bot, through Telegram's creator bot — where an account session is configured.

    Only ever on this request: the module never creates one on its own initiative, because the
    account being automated is the operator's own and Telegram limits accounts for exactly that.
    """
    settings = request.app.state.settings
    conversation = creator.from_settings(settings)
    if conversation is None:
        # The refusal `bots.create` would raise anyway; here it is also what makes a conversation
        # object exist to pass at all.
        raise deps.refusal(CreatingBotsUnavailable())

    async with deps.connection(request.app.state.pool) as conn:
        try:
            created = await bots.create(
                conn,
                conversation,
                title=body.title,
                username=body.username,
                can_create=settings.can_create_bots,
                ceiling=settings.max_bots,
            )
        except ValueError as err:
            # Telegram's username rule, refused before a word was sent to the creator bot.
            raise deps.bad_request(str(err)) from err
        except GatewayError as err:
            raise deps.refusal(err) from err
    request.app.state.watcher.watch(created)
    return BotOut.of(created)


@router.delete(
    "/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}, 501: {"model": Problem}, 502: {"model": Problem}},
)
async def remove(request: Request, username: str) -> Response:
    """Removes the bot from Telegram and from here, and its destinations with it.

    The same road as creating: only the account session can delete a bot, and a row dropped here
    while the bot lives on Telegram would still count against the account's ceiling.
    """
    settings = request.app.state.settings
    async with deps.connection(request.app.state.pool) as conn:
        existing = await store.bot_by_username(conn, username)
        if existing is None:
            raise deps.not_found(f"@{username} is not a bot this gateway holds")

        conversation = creator.from_settings(settings)
        if conversation is None:
            raise deps.refusal(CreatingBotsUnavailable())
        try:
            await bots.destroy(
                conn, conversation, existing=existing, can_create=settings.can_create_bots
            )
        except GatewayError as err:
            raise deps.refusal(err) from err
    request.app.state.watcher.forget(existing.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
