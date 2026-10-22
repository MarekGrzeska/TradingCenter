"""Stand-ins for Telegram, so this module can be tested without a third party's uptime. Structural
rather than a subclass: what the module uses is three methods."""

from __future__ import annotations

from typing import Any

from telegram_gateway.bot_api import Delivered


class FakeBotApi:
    """Answers from a script. Each method returns what it was given, or raises what it was given."""

    def __init__(
        self,
        *,
        send: Exception | Delivered | None = None,
        me: dict[str, Any] | Exception | None = None,
        updates: list[list[dict[str, Any]]] | None = None,
        chat: dict[str, Any] | Exception | None = None,
    ) -> None:
        self._send = send
        self._me = me
        self._chat = chat
        self.chats_asked: list[int] = []
        # A list per poll, so a test can script "nothing, then a start command".
        self._updates = list(updates or [])
        self.sent: list[tuple[str, int, str]] = []
        self.update_calls: list[tuple[str, int]] = []

    async def send_message(self, token: str, *, chat_id: int, text: str) -> Delivered:
        self.sent.append((token, chat_id, text))
        if isinstance(self._send, Exception):
            raise self._send
        return self._send or Delivered(message_id=len(self.sent), chat_id=chat_id)

    async def get_me(self, token: str) -> dict[str, Any]:
        if isinstance(self._me, Exception):
            raise self._me
        return self._me or {"id": int(token.split(":")[0]), "username": "afakebot", "first_name": "A"}

    async def get_chat(self, token: str, *, chat_id: int) -> dict[str, Any]:
        self.chats_asked.append(chat_id)
        if isinstance(self._chat, Exception):
            raise self._chat
        return self._chat or {"id": chat_id, "type": "private", "username": "someone", "first_name": "Some", "last_name": "One"}

    async def get_updates(
        self, token: str, *, offset: int, timeout: int
    ) -> list[dict[str, Any]]:
        self.update_calls.append((token, offset))
        return self._updates.pop(0) if self._updates else []


def start_update(
    update_id: int, *, chat_id: int, payload: str, username: str | None = None, first_name: str = "Marek"
) -> dict[str, Any]:
    """One `/start <payload>` as Telegram delivers it, from a person."""
    sender = {"id": chat_id, "is_bot": False, "first_name": first_name, **({"username": username} if username else {})}
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": sender,
            "chat": {"id": chat_id, "type": "private", "first_name": first_name},
            "text": f"/start {payload}".strip(),
        },
    }


class FakeCreatorBot:
    """@BotFather from a script. What it says is the whole interface: the module reads a token out of
    a sentence, so a test's lever is the sentence."""

    def __init__(
        self,
        *,
        reply: str | Exception = "",
        on_delete: str | Exception = "Done!",
        on_revoke: str | Exception = "",
    ) -> None:
        self._reply = reply
        self._on_delete = on_delete
        self._on_revoke = on_revoke
        self.created: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.revoked: list[str] = []

    async def create(self, *, title: str, username: str) -> str:
        self.created.append((title, username))
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply

    async def delete(self, *, username: str) -> str:
        self.deleted.append(username)
        if isinstance(self._on_delete, Exception):
            raise self._on_delete
        return self._on_delete

    async def revoke(self, *, username: str) -> str:
        self.revoked.append(username)
        if isinstance(self._on_revoke, Exception):
            raise self._on_revoke
        return self._on_revoke


def botfather_success(token: str, username: str = "alertsbot") -> str:
    """What @BotFather actually answers — a paragraph of prose with the token in the middle of it."""
    return (
        f"Done! Congratulations on your new bot. You will find it at t.me/{username}. "
        "You can now add a description, about section and profile picture for your bot.\n\n"
        f"Use this token to access the HTTP API:\n{token}\n"
        "Keep your token secure and store it safely, it can be used by anyone to control your bot."
    )


class RecordingWatcher:
    """The long-poll supervisor as the routes use it — two calls, and a test that reads them back.

    A real `Watcher` here would start a task polling a fake Telegram in a tight loop for as long as
    the test ran.
    """

    def __init__(self) -> None:
        self.watching: list[str] = []
        self.forgotten: list[int] = []

    def watch(self, bot) -> None:
        self.watching.append(bot.username)

    def forget(self, bot_id: int) -> None:
        self.forgotten.append(bot_id)


class FakeLoginClient:
    """One login from a script: the code Telegram wants, whether the account has a password, and what it says to a
    wrong guess. Records every call, so a test can see that a code was never kept anywhere but here."""

    def __init__(
        self,
        *,
        code: str = "12345",
        password: str | None = None,
        send_error: Exception | None = None,
        username: str = "ownerbot_account",
        can_resend: bool = True,
    ) -> None:
        self._can_resend = can_resend
        self._code = code
        self._password = password
        self._send_error = send_error
        self._username = username
        self.phone: str | None = None
        self.disconnected = False
        self.resends = 0
        self.expire_first = False

    async def send_code(self, phone: str):
        from telegram_gateway.account import CodeSent

        if self._send_error is not None:
            raise self._send_error
        self.phone = phone
        return CodeSent(delivery="app", can_resend=self._can_resend)

    async def resend_code(self):
        from telegram_gateway.account import CodeSent

        self.resends += 1
        return CodeSent(delivery="sms", can_resend=False)

    async def sign_in_code(self, code: str):
        from telegram_gateway.account import Identity
        from telegram_gateway.errors import LoginRefused

        if code != self._code:
            raise LoginRefused("the code is wrong")
        if self._password is not None:
            return None
        return Identity(username=self._username, phone=self.phone or "", session="SESSION-STRING-1")

    async def sign_in_password(self, password: str):
        from telegram_gateway.account import Identity
        from telegram_gateway.errors import LoginRefused

        if password != self._password:
            raise LoginRefused("the password is wrong")
        return Identity(username=self._username, phone=self.phone or "", session="SESSION-STRING-1")

    async def start_qr(self):
        import asyncio
        from datetime import UTC, datetime, timedelta

        from telegram_gateway.account import QrTicket

        self.scanned = asyncio.Event()
        self.qr_tickets = 1
        return QrTicket(url="tg://login?token=first", expires_at=datetime.now(UTC) + timedelta(seconds=30))

    async def wait_qr(self):
        from telegram_gateway.account import Identity

        if self.expire_first:
            self.expire_first = False
            raise TimeoutError
        await self.scanned.wait()
        if self._password is not None:
            return None
        return Identity(username=self._username, phone="+48123456789", session="SESSION-STRING-1")

    async def renew_qr(self):
        from datetime import UTC, datetime, timedelta

        from telegram_gateway.account import QrTicket

        self.qr_tickets += 1
        return QrTicket(url=f"tg://login?token=renewed{self.qr_tickets}", expires_at=datetime.now(UTC) + timedelta(seconds=30))

    async def disconnect(self) -> None:
        self.disconnected = True


class FakePlatform:
    """The owner account as the gateway reaches it: a login to hand out, a creator bot to converse with, and a
    log-out that records the session it ended."""

    def __init__(
        self,
        *,
        login: FakeLoginClient | None = None,
        creator: FakeCreatorBot | None = None,
        log_out_error: Exception | None = None,
    ) -> None:
        self.login = login or FakeLoginClient()
        self.conversation = creator or FakeCreatorBot()
        self.log_out_error = log_out_error
        self.ended: list[str] = []
        self.creator_sessions: list[str] = []

    def login_client(self, api_id: int, api_hash: str):
        return self.login

    def creator(self, api_id: int, api_hash: str, session: str):
        self.creator_sessions.append(session)
        return self.conversation

    async def log_out(self, api_id: int, api_hash: str, session: str) -> None:
        if self.log_out_error is not None:
            raise self.log_out_error
        self.ended.append(session)
