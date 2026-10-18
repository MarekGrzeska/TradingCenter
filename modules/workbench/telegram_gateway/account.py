"""The account that owns the bots: logging it in from the terminal, keeping its session, and saying whether it can be used.

Telegram's own steps are the shape — phone, code, and a password when the account has one — and the login between them
lives in this process's memory for ten minutes. In the database would be half a login in a nightly dump; lost to a
restart is one more tap. The session it produces is stored encrypted (`session_crypto`) and read by exactly one function.

Telethon is imported inside the methods that use it, like `creator.py`: a deployment that never logs an account in never
loads it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Protocol

from tc_runtime.db import Conn

from . import session_crypto, store
from .config import Settings
from .creator import CreatorBot, TelethonCreatorBot
from .errors import (
    CreatingBotsUnavailable,
    LoginNotInProgress,
    LoginRefused,
    LoginUnavailable,
    SessionRejected,
)

log = logging.getLogger(__name__)

LOGIN_LIFETIME = timedelta(minutes=10)
_PHONE = re.compile(r"^\+\d{7,15}$")


class AccountStatus(str, Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    # Something is stored and cannot be used: the key changed, the row is damaged, or Telegram ended the session.
    NEEDS_LOGIN = "needs_login"


@dataclass(frozen=True, slots=True)
class Identity:
    """A finished login. `session` leaves this module only into `session_crypto.encrypt`."""

    username: str
    phone: str
    session: str = ""

    def __repr__(self) -> str:  # a session in a traceback is a session in a log
        return f"Identity(username={self.username!r}, phone=<masked>, session=<hidden>)"


@dataclass(frozen=True, slots=True)
class AccountView:
    status: AccountStatus
    username: str | None = None
    phone_masked: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CodeSent:
    """Where Telegram sent the code, and whether it would send it another way if asked."""

    delivery: str
    can_resend: bool


@dataclass(frozen=True, slots=True)
class QrTicket:
    """A login token as `tg://login?token=…` and when it stops working (about half a minute). The token logs in whoever
    scans it *into this server*, so it is shown to the operator and never logged."""

    url: str
    expires_at: datetime


@dataclass
class QrState:
    """Where a QR login is: `waiting` for a scan, `password` wanted, `done` with an identity to save, or `failed`."""

    status: str
    ticket: QrTicket | None = None
    identity: Identity | None = None
    reason: str | None = None


# Where Telegram said the code went. `app` is a message from "Telegram" in an app already logged in to the account — and
# the one that fails silently when nobody is looking at that account.
DELIVERIES = ("app", "sms", "call", "other")


class LoginClient(Protocol):
    """One login with Telegram, as the manager drives it. A protocol because the real one needs a phone."""

    async def send_code(self, phone: str) -> CodeSent:
        """Asks for a code and returns where Telegram sent it (one of `DELIVERIES`)."""
        ...

    async def resend_code(self) -> CodeSent:
        """Asks Telegram for the next way of delivering the same code (app → SMS → call), and says which."""
        ...

    async def sign_in_code(self, code: str) -> Identity | None:
        """The identity, or `None` when the account has a password and wants it next."""
        ...

    async def sign_in_password(self, password: str) -> Identity: ...

    async def start_qr(self) -> QrTicket:
        """Asks Telegram for a login token to show as a QR code. No code is sent anywhere."""
        ...

    async def wait_qr(self) -> Identity | None:
        """Waits until an app logged in to the account scans the code: the identity, or `None` when the account has a
        password and wants it next. Raises `TimeoutError` when the token expires first."""
        ...

    async def renew_qr(self) -> QrTicket: ...

    async def disconnect(self) -> None: ...


class AccountPlatform(Protocol):
    """Everything that talks to Telegram as the owner account. One object so a test replaces one thing."""

    def login_client(self, api_id: int, api_hash: str) -> LoginClient: ...

    def creator(self, api_id: int, api_hash: str, session: str) -> CreatorBot: ...

    async def log_out(self, api_id: int, api_hash: str, session: str) -> None: ...


def mask_phone(phone: str) -> str:
    """The number with at most its last four digits showing — nothing in this module needs the rest."""
    digits = phone.lstrip("+")
    return "+" + "•" * max(len(digits) - 4, 0) + digits[-4:]


def valid_phone(phone: str) -> str:
    candidate = phone.replace(" ", "").replace("-", "")
    if not _PHONE.fullmatch(candidate):
        raise LoginRefused("the number must be in international form, like +48123456789")
    return candidate


class LoginManager:
    """At most one login at a time, for ten minutes, in memory."""

    def __init__(
        self,
        factory: Callable[[int, str], LoginClient],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._lock = asyncio.Lock()
        self._client: LoginClient | None = None
        self._deadline: datetime | None = None
        self._qr: QrState | None = None
        self._qr_task: asyncio.Task | None = None

    async def begin_qr(self, *, api_id: int, api_hash: str) -> QrTicket:
        """A login by QR code: no code is sent, an app already logged in to the account scans this server's token. The
        token is renewed by itself until the ten minutes run out."""
        async with self._lock:
            await self._drop()
            client = self._factory(api_id, api_hash)
            try:
                ticket = await client.start_qr()
            except BaseException:
                await client.disconnect()
                raise
            self._client = client
            self._deadline = self._clock() + LOGIN_LIFETIME
            self._qr = QrState(status="waiting", ticket=ticket)
            self._qr_task = asyncio.create_task(self._watch_qr(client), name="telegram-qr-login")
            log.info("a QR login is waiting for a scan")
            return ticket

    async def _watch_qr(self, client: LoginClient) -> None:
        while True:
            try:
                identity = await client.wait_qr()
            except TimeoutError:
                if self._qr is None or self._deadline is None or self._clock() >= self._deadline:
                    if self._qr is not None:
                        self._qr.status, self._qr.reason = "failed", "the login expired — start again"
                    return
                try:
                    ticket = await client.renew_qr()
                except LoginRefused as err:
                    if self._qr is not None:
                        self._qr.status, self._qr.reason = "failed", str(err)
                    return
                if self._qr is not None:
                    self._qr.ticket = ticket
                continue
            except LoginRefused as err:
                if self._qr is not None:
                    self._qr.status, self._qr.reason = "failed", str(err)
                return
            if self._qr is None:
                return
            if identity is None:
                self._qr.status = "password"
                log.info("the QR login was scanned; the account wants its password")
                return
            self._qr.status, self._qr.identity = "done", identity
            log.info("the QR login was scanned")
            return

    async def qr_state(self) -> QrState:
        """The QR login as it stands. A `done` state is handed over once: the identity leaves this object with it."""
        async with self._lock:
            if self._qr is None:
                raise LoginNotInProgress()
            state = QrState(
                status=self._qr.status, ticket=self._qr.ticket, identity=self._qr.identity, reason=self._qr.reason
            )
            if state.status in ("done", "failed"):
                await self._drop()
            return state

    async def begin(self, phone: str, *, api_id: int, api_hash: str) -> CodeSent:
        number = valid_phone(phone)
        async with self._lock:
            await self._drop()
            client = self._factory(api_id, api_hash)
            try:
                delivery = await client.send_code(number)
            except BaseException:
                await client.disconnect()
                raise
            self._client = client
            self._deadline = self._clock() + LOGIN_LIFETIME
            log.info("a login code was sent by %s", delivery.delivery)
            return delivery

    async def resend(self) -> CodeSent:
        """The same login, asked again for another way of delivering the code. Extends nothing: the ten minutes run
        from the number."""
        async with self._lock:
            client = await self._live()
            delivery = await client.resend_code()
            log.info("a login code was sent again by %s", delivery.delivery)
            return delivery

    async def code(self, code: str) -> Identity | None:
        async with self._lock:
            client = await self._live()
            identity = await client.sign_in_code(code.strip())
            if identity is not None:
                await self._drop()
            return identity

    async def password(self, password: str) -> Identity:
        async with self._lock:
            client = await self._live()
            identity = await client.sign_in_password(password)
            await self._drop()
            return identity

    async def close(self) -> None:
        async with self._lock:
            await self._drop()

    async def _live(self) -> LoginClient:
        if self._client is None or self._deadline is None or self._clock() >= self._deadline:
            await self._drop()
            raise LoginNotInProgress()
        return self._client

    async def _drop(self) -> None:
        task, self._qr_task, self._qr = self._qr_task, None, None
        if task is not None and not task.done():
            task.cancel()
        client, self._client, self._deadline = self._client, None, None
        if client is not None:
            await client.disconnect()


# --- what is stored ----------------------------------------------------------------------------------


async def view(conn: Conn, settings: Settings) -> AccountView:
    """Whether the stored account can be used, answered without asking Telegram: the key opens it, and Telegram has
    not already refused it. A session ended from the phone is only found out when it is used."""
    record = await store.get_account(conn)
    if record is None:
        return AccountView(AccountStatus.LOGGED_OUT)
    base = {"username": record.username, "phone_masked": record.phone_masked}
    if settings.telegram_session_key is None:
        return AccountView(AccountStatus.NEEDS_LOGIN, reason="TELEGRAM_SESSION_KEY is not set", **base)
    token = await store.encrypted_session(conn)
    if token is None or session_crypto.decrypt(settings.telegram_session_key, token) is None:
        return AccountView(
            AccountStatus.NEEDS_LOGIN,
            reason="the stored session cannot be opened with this key (the key changed)",
            **base,
        )
    if record.rejected_at is not None:
        return AccountView(AccountStatus.NEEDS_LOGIN, reason="Telegram rejected the session", **base)
    return AccountView(AccountStatus.LOGGED_IN, **base)


async def usable_session(conn: Conn, settings: Settings) -> str:
    """The decrypted session, or the refusal that says which step is missing."""
    if not settings.api_credentials_configured:
        raise CreatingBotsUnavailable("TELEGRAM_API_ID and TELEGRAM_API_HASH are not set")
    current = await view(conn, settings)
    if current.status is AccountStatus.LOGGED_OUT:
        raise CreatingBotsUnavailable("no Telegram account is logged in")
    if current.status is AccountStatus.NEEDS_LOGIN:
        raise CreatingBotsUnavailable(f"the account needs logging in again ({current.reason})")
    assert settings.telegram_session_key is not None  # LOGGED_IN is only reached with a key that opens it
    token = await store.encrypted_session(conn)
    assert token is not None
    session = session_crypto.decrypt(settings.telegram_session_key, token)
    assert session is not None
    return session


def require_login_settings(settings: Settings) -> tuple[int, str, str]:
    """Application id, hash and the session key — checked before Telegram is spoken to, by name."""
    if not settings.api_credentials_configured:
        raise LoginUnavailable("TELEGRAM_API_ID and TELEGRAM_API_HASH")
    if settings.telegram_session_key is None:
        raise LoginUnavailable("TELEGRAM_SESSION_KEY")
    assert settings.telegram_api_id is not None and settings.telegram_api_hash is not None
    return settings.telegram_api_id, settings.telegram_api_hash, settings.telegram_session_key


async def save_login(conn: Conn, settings: Settings, identity: Identity) -> None:
    _, _, key = require_login_settings(settings)
    await store.save_account(
        conn,
        session_encrypted=session_crypto.encrypt(key, identity.session),
        username=identity.username,
        phone_masked=mask_phone(identity.phone),
    )
    log.info("the owner account @%s is logged in", identity.username)


async def log_out(
    conn: Conn, settings: Settings, platform: AccountPlatform
) -> bool:
    """Removes the stored session, and ends it at Telegram if that can be done. Returns whether Telegram was told.

    The row goes either way: an account the operator asked to forget must not stay usable here because Telegram was
    briefly unreachable. The caller says what did not happen, so the session can be ended from the phone.
    """
    told = False
    session: str | None = None
    if settings.api_credentials_configured and settings.telegram_session_key is not None:
        token = await store.encrypted_session(conn)
        if token is not None:
            session = session_crypto.decrypt(settings.telegram_session_key, token)
    if session is not None:
        try:
            assert settings.telegram_api_id is not None and settings.telegram_api_hash is not None
            await platform.log_out(settings.telegram_api_id, settings.telegram_api_hash, session)
            told = True
        except Exception as err:  # noqa: BLE001 - Telegram unreachable or the session already dead: forget it either way
            log.warning("could not end the session at Telegram: %s", type(err).__name__)
    await store.delete_account(conn)
    return told


# --- the real one ------------------------------------------------------------------------------------


class TelethonLoginClient:
    def __init__(self, api_id: int, api_hash: str) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._client = None
        self._phone = ""
        self._hash = ""
        self._qr = None

    async def send_code(self, phone: str) -> CodeSent:
        from telethon import TelegramClient
        from telethon.errors import RPCError
        from telethon.sessions import StringSession

        self._client = TelegramClient(StringSession(), self._api_id, self._api_hash)
        try:
            await self._client.connect()
            sent = await self._client.send_code_request(phone)
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        except (OSError, TimeoutError) as err:
            # A network that did not answer is a reason the operator can act on, not an unhandled error with no words.
            raise LoginRefused("Telegram could not be reached — try again in a moment") from err
        self._phone = phone
        self._hash = sent.phone_code_hash
        return CodeSent(delivery=_delivery_of(sent), can_resend=getattr(sent, "next_type", None) is not None)

    async def resend_code(self) -> CodeSent:
        from telethon.errors import RPCError

        assert self._client is not None
        try:
            # A second request for a phone Telethon already holds a hash for is a resend: Telegram moves to the next
            # delivery it offers.
            sent = await self._client.send_code_request(self._phone)
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        except (OSError, TimeoutError) as err:
            raise LoginRefused("Telegram could not be reached — try again in a moment") from err
        if sent.phone_code_hash:
            self._hash = sent.phone_code_hash
        return CodeSent(delivery=_delivery_of(sent), can_resend=getattr(sent, "next_type", None) is not None)

    async def sign_in_code(self, code: str) -> Identity | None:
        from telethon.errors import RPCError, SessionPasswordNeededError

        assert self._client is not None
        try:
            await self._client.sign_in(self._phone, code, phone_code_hash=self._hash)
        except SessionPasswordNeededError:
            return None
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        except (OSError, TimeoutError) as err:
            raise LoginRefused("Telegram could not be reached — the login is still open, try the code again") from err
        return await self._identity()

    async def sign_in_password(self, password: str) -> Identity:
        from telethon.errors import RPCError

        assert self._client is not None
        try:
            await self._client.sign_in(password=password)
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        except (OSError, TimeoutError) as err:
            raise LoginRefused("Telegram could not be reached — the login is still open, try the password again") from err
        return await self._identity()

    async def _identity(self) -> Identity:
        assert self._client is not None
        me = await self._client.get_me()
        name = getattr(me, "username", None) or getattr(me, "first_name", None) or str(getattr(me, "id", ""))
        # A QR login never typed a number: the account says its own.
        own = getattr(me, "phone", None)
        phone = self._phone or (f"+{own}" if own else "")
        # Telethon types `session` as optional and `get_me` as a peer; both are a logged-in user here.
        session = self._client.session.save()  # pyright: ignore[reportAttributeAccessIssue]
        return Identity(username=str(name), phone=phone, session=session)

    async def start_qr(self) -> QrTicket:
        from telethon import TelegramClient
        from telethon.errors import RPCError
        from telethon.sessions import StringSession

        self._client = TelegramClient(StringSession(), self._api_id, self._api_hash)
        try:
            await self._client.connect()
            self._qr = await self._client.qr_login()
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        except (OSError, TimeoutError) as err:
            raise LoginRefused("Telegram could not be reached — try again in a moment") from err
        return QrTicket(url=self._qr.url, expires_at=self._qr.expires)

    async def wait_qr(self) -> Identity | None:
        from telethon.errors import RPCError, SessionPasswordNeededError

        assert self._qr is not None
        try:
            await self._qr.wait()
        except SessionPasswordNeededError:
            return None
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        return await self._identity()

    async def renew_qr(self) -> QrTicket:
        from telethon.errors import RPCError

        assert self._qr is not None
        try:
            await self._qr.recreate()
        except RPCError as err:
            raise LoginRefused(_telethon_words(err)) from err
        return QrTicket(url=self._qr.url, expires_at=self._qr.expires)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()  # type: ignore[misc]


def _delivery_of(sent) -> str:
    """Where Telegram says it sent the code. By the class of the answer, which is Telegram's vocabulary; anything this
    does not know is `other` rather than a guess."""
    kind = type(sent.type).__name__
    if kind == "SentCodeTypeApp":
        return "app"
    if kind == "SentCodeTypeSms":
        return "sms"
    if kind in ("SentCodeTypeCall", "SentCodeTypeFlashCall", "SentCodeTypeMissedCall"):
        return "call"
    return "other"


def _telethon_words(err: Exception) -> str:
    """What Telegram said, by its class — never `str(err)`, which is free to quote what was sent. The few the
    operator can act on get a sentence."""
    name = type(err).__name__
    known = {
        "PhoneCodeInvalidError": "the code is wrong",
        "PhoneCodeExpiredError": "the code has expired — start again from the phone number",
        "PasswordHashInvalidError": "the password is wrong",
        "PhoneNumberInvalidError": "Telegram does not accept that number",
        "ApiIdInvalidError": "Telegram does not accept this application id and hash",
        "SendCodeUnavailableError": "Telegram has no other way of sending the code — wait a few minutes and start again",
    }
    if name in known:
        return known[name]
    wait = getattr(err, "seconds", None)
    return f"{name} (wait {wait}s)" if wait else name


class TelethonPlatform:
    """The real owner-account platform."""

    def login_client(self, api_id: int, api_hash: str) -> LoginClient:
        return TelethonLoginClient(api_id, api_hash)

    def creator(self, api_id: int, api_hash: str, session: str) -> CreatorBot:
        return TelethonCreatorBot(api_id=api_id, api_hash=api_hash, session=session)

    async def log_out(self, api_id: int, api_hash: str, session: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(session), api_id, api_hash)
        await client.connect()
        try:
            if await client.is_user_authorized():
                await client.log_out()
        finally:
            await client.disconnect()  # type: ignore[misc]


__all__ = [
    "AccountPlatform",
    "AccountStatus",
    "AccountView",
    "Identity",
    "LoginClient",
    "LoginManager",
    "SessionRejected",
    "TelethonPlatform",
    "log_out",
    "mask_phone",
    "save_login",
    "usable_session",
    "view",
]
