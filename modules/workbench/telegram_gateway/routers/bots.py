"""The bots this gateway may speak as. Every route here is REST and stays REST — a bot outlives the
conversation that asked for it, so `telegram-gateway-tools` keeps the whole of this off that surface.

Two ways in, and they are not two flavours of one: adopting a token the operator pasted always works,
creating one needs the account session that `/state` reports on.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from tc_runtime.db import Conn

from .. import account, bots, store
from ..contract import AdoptBotRequest, BotOut, NewBotRequest, Problem
from ..errors import GatewayError, SessionRejected
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


async def owner_conversation(request: Request, conn: Conn):
    """The conversation with the creator bot, held by the logged-in owner account - or the refusal that says which
    step is missing. Nothing is asked of Telegram before this returns."""
    settings = request.app.state.settings
    session = await account.usable_session(conn, settings)
    return request.app.state.platform.creator(
        settings.telegram_api_id, settings.telegram_api_hash, session
    )


async def _rejected(conn: Conn, err: GatewayError) -> HTTPException:
    """Telegram refused the session while it was used: remembered, so the state route says so afterwards."""
    if isinstance(err, SessionRejected):
        await store.mark_account_rejected(conn)
    return deps.refusal(err)


@router.post(
    "/created",
    response_model=BotOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": Problem},
        422: {"model": Problem},
        501: {"model": Problem},
        502: {"model": Problem},
    },
)
async def create(request: Request, body: NewBotRequest) -> BotOut:
    """A new bot, through Telegram's creator bot - where the owner account is logged in.

    Only ever on this request: the module never creates one on its own initiative, because the
    account being automated is the operator's own and Telegram limits accounts for exactly that.
    """
    settings = request.app.state.settings
    async with deps.connection(request.app.state.pool) as conn:
        try:
            conversation = await owner_conversation(request, conn)
            created = await bots.create(
                conn,
                conversation,
                title=body.title,
                username=body.username,
                can_create=True,
                ceiling=settings.max_bots,
            )
        except ValueError as err:
            # Telegram's username rule, refused before a word was sent to the creator bot.
            raise deps.bad_request(str(err)) from err
        except GatewayError as err:
            raise await _rejected(conn, err) from err
    request.app.state.watcher.watch(created)
    return BotOut.of(created)


@router.post(
    "/{username}/token",
    response_model=BotOut,
    responses={
        404: {"model": Problem},
        409: {"model": Problem},
        501: {"model": Problem},
        502: {"model": Problem},
    },
)
async def rotate(request: Request, username: str) -> BotOut:
    """A new token for a bot, through the creator bot. The old one stops working at once; the bot's destinations
    and assignments are untouched, so nobody taps a link again."""
    async with deps.connection(request.app.state.pool) as conn:
        existing = await store.bot_by_username(conn, username)
        if existing is None:
            raise deps.not_found(f"@{username} is not a bot this gateway holds")
        try:
            conversation = await owner_conversation(request, conn)
            rotated = await bots.rotate(
                conn, request.app.state.telegram, conversation, existing=existing
            )
        except GatewayError as err:
            raise await _rejected(conn, err) from err
    return BotOut.of(rotated)


@router.delete(
    "/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": Problem},
        409: {"model": Problem},
        501: {"model": Problem},
        502: {"model": Problem},
    },
)
async def remove(request: Request, username: str) -> Response:
    """Removes the bot from Telegram and from here, and its destinations with it.

    The same road as creating: only the owner account can delete a bot, and a row dropped here
    while the bot lives on Telegram would still count against the account's ceiling.
    """
    async with deps.connection(request.app.state.pool) as conn:
        existing = await store.bot_by_username(conn, username)
        if existing is None:
            raise deps.not_found(f"@{username} is not a bot this gateway holds")

        try:
            conversation = await owner_conversation(request, conn)
            await bots.destroy(conn, conversation, existing=existing, can_create=True)
        except GatewayError as err:
            raise await _rejected(conn, err) from err
    request.app.state.watcher.forget(existing.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
