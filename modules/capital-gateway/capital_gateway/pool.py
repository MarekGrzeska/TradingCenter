"""One capital.com session per account a caller names, beside the default session whose account is the
"active" one. The account is session state at the provider (measured 28 October 2026: sessions on two
accounts at once, an order on one invisible from the other), so a session per account is what lets two
callers trade two accounts without moving each other's."""

from __future__ import annotations

import asyncio

from .adapter import CapitalAdapter
from .client import REQUESTS_PER_SECOND, CapitalClient
from .config import Settings
from .errors import GatewayError
from .rategate import RateGate


class SessionPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # One budget for the whole login: the provider counts it per login, not per session.
        self._gate = RateGate(REQUESTS_PER_SECOND)
        self._login_gate = RateGate(1)
        self.default = CapitalAdapter(self._client())
        # Never switched, so nothing done to the active account can reach what the stream publishes.
        self.stream = self._client()
        self._by_account: dict[str, CapitalAdapter] = {}
        self._known: set[str] = set()
        self._lock = asyncio.Lock()

    def _client(self, account_id: str | None = None) -> CapitalClient:
        return CapitalClient(
            self._settings, gate=self._gate, login_gate=self._login_gate, account_id=account_id
        )

    async def for_account(self, account_id: str) -> CapitalAdapter:
        """The session standing on `account_id`. An id the provider does not list is refused before any
        login: falling back to the active account would put the caller's order on somebody else's."""
        async with self._lock:
            if (adapter := self._by_account.get(account_id)) is not None:
                return adapter
            if account_id not in self._known:
                self._known = {a.id for a in await self.default.list_accounts()}
            if account_id not in self._known:
                raise GatewayError(f"no such account: {account_id}", status_code=400)
            adapter = self._by_account[account_id] = CapitalAdapter(self._client(account_id))
            return adapter

    async def aclose(self) -> None:
        for adapter in (self.default, *self._by_account.values()):
            await adapter.aclose()
        await self.stream.aclose()
