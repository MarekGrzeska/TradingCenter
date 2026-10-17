"""Logging the owner account in, from the terminal, and out again. REST alone: a session outlives the
conversation that asked for it, and whoever holds it can write as the bots the operator trusts.

The steps are Telegram's and so is the wording of every refusal. Nothing here logs, echoes or stores a code or a
password; the session leaves `account.py` only into `session_crypto`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status

from .. import account
from ..contract import (
    AccountOut,
    LoginCodeRequest,
    LoginPasswordRequest,
    LoginStartRequest,
    LoginStepOut,
    LogoutOut,
    Problem,
)
from ..errors import GatewayError
from . import deps

router = APIRouter(prefix="/account", tags=["account"])

_REFUSALS: dict[int | str, dict[str, Any]] = {409: {"model": Problem}, 501: {"model": Problem}}


async def account_out(conn, settings) -> AccountOut:
    current = await account.view(conn, settings)
    return AccountOut(
        status=current.status.value,  # pyright: ignore[reportArgumentType]
        username=current.username,
        phone=current.phone_masked,
        reason=current.reason,
        session_key_configured=settings.session_key_configured,
        api_credentials_configured=settings.api_credentials_configured,
    )


@router.get("", response_model=AccountOut)
async def read(request: Request) -> AccountOut:
    async with deps.connection(request.app.state.pool) as conn:
        return await account_out(conn, request.app.state.settings)


@router.post("/login", response_model=LoginStepOut, responses=_REFUSALS)
async def begin(request: Request, body: LoginStartRequest) -> LoginStepOut:
    """Asks Telegram to send a code to the number. Replaces a login already in progress."""
    settings = request.app.state.settings
    try:
        api_id, api_hash, _ = account.require_login_settings(settings)
        await request.app.state.login.begin(body.phone, api_id=api_id, api_hash=api_hash)
    except GatewayError as err:
        raise deps.refusal(err) from err
    return LoginStepOut(step="code")


@router.post("/login/code", response_model=LoginStepOut, responses=_REFUSALS)
async def code(request: Request, body: LoginCodeRequest) -> LoginStepOut:
    """The code Telegram sent. A wrong one leaves the login open for another; an account with a password
    answers `step: password`."""
    settings = request.app.state.settings
    try:
        identity = await request.app.state.login.code(body.code)
        if identity is None:
            return LoginStepOut(step="password")
        async with deps.connection(request.app.state.pool) as conn:
            await account.save_login(conn, settings, identity)
            return LoginStepOut(step="done", account=await account_out(conn, settings))
    except GatewayError as err:
        raise deps.refusal(err) from err


@router.post("/login/password", response_model=LoginStepOut, responses=_REFUSALS)
async def password(request: Request, body: LoginPasswordRequest) -> LoginStepOut:
    settings = request.app.state.settings
    try:
        identity = await request.app.state.login.password(body.password)
        async with deps.connection(request.app.state.pool) as conn:
            await account.save_login(conn, settings, identity)
            return LoginStepOut(step="done", account=await account_out(conn, settings))
    except GatewayError as err:
        raise deps.refusal(err) from err


@router.delete("", response_model=LogoutOut, status_code=status.HTTP_200_OK)
async def log_out(request: Request) -> LogoutOut:
    """Forgets the account here and ends its session at Telegram when Telegram can be reached. The bots stay;
    only the ability to create, delete and rotate them goes until the account is logged in again."""
    async with deps.connection(request.app.state.pool) as conn:
        told = await account.log_out(conn, request.app.state.settings, request.app.state.platform)
    return LogoutOut(ended_at_telegram=told)
