"""One capital.com session per account a caller names, beside the default session whose account is the
"active" one. The account is session state at the provider (measured 28 October 2026: sessions on two
accounts at once, an order on one invisible from the other), so a session per account is what lets two
callers trade two accounts without moving each other's."""

from __future__ import annotations

import asyncio

from .adapter import CapitalAdapter
from .client import REQUESTS_PER_SECOND, CapitalClient
from .config import LIVE_ENVIRONMENT, Settings
from .errors import GatewayError
from .rategate import RateGate


class SessionPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # One budget for the whole login: the provider counts it per login, not per session.
        self._gate = RateGate(REQUESTS_PER_SECOND)
        self._login_gate = RateGate(1)
        # On the live account the default session is pinned to the one configured account, and is put back on it after
        # every renewal; a fresh login opening on some other live account must not be where an order lands.
        self._pinned = settings.live_account_id if settings.capital_environment == LIVE_ENVIRONMENT else None
        self.default = CapitalAdapter(self._client(self._pinned))
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
        if self._pinned is not None:
            if account_id != self._pinned:
                raise GatewayError(
                    f"refused: this process trades only the live account {self._pinned}, not {account_id}",
                    status_code=400,
                )
            return self.default
        # Outside the lock: a pooled account must not queue behind another account's first login.
        if (adapter := self._by_account.get(account_id)) is not None:
            return adapter
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
