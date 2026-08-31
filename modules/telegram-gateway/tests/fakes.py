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
    ) -> None:
        self._send = send
        self._me = me
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

    async def get_updates(
        self, token: str, *, offset: int, timeout: int
    ) -> list[dict[str, Any]]:
        self.update_calls.append((token, offset))
        return self._updates.pop(0) if self._updates else []


def start_update(update_id: int, *, chat_id: int, payload: str) -> dict[str, Any]:
    """One `/start <payload>` as Telegram delivers it."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id, "type": "private"},
            "text": f"/start {payload}".strip(),
        },
    }


class FakeCreatorBot:
    """@BotFather from a script. What it says is the whole interface: the module reads a token out of
    a sentence, so a test's lever is the sentence."""

    def __init__(self, *, reply: str | Exception = "", on_delete: str | Exception = "Done!") -> None:
        self._reply = reply
        self._on_delete = on_delete
        self.created: list[tuple[str, str]] = []
        self.deleted: list[str] = []

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


def botfather_success(token: str, username: str = "alertsbot") -> str:
    """What @BotFather actually answers — a paragraph of prose with the token in the middle of it."""
    return (
        f"Done! Congratulations on your new bot. You will find it at t.me/{username}. "
        "You can now add a description, about section and profile picture for your bot.\n\n"
        f"Use this token to access the HTTP API:\n{token}\n"
        "Keep your token secure and store it safely, it can be used by anyone to control your bot."
    )
