"""Thin async client for the capital.com REST API. Low-level on purpose: every method hands back
the raw ``httpx.Response``, and it owns the stateful session tokens callers never see."""

from __future__ import annotations

import asyncio

import httpx

from .config import Settings
from .rategate import RateGate

API_PREFIX = "/api/v1"
_TIMEOUT_SECONDS = 20.0
_REQUESTS_PER_SECOND = 10


class CapitalClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._http = httpx.AsyncClient(base_url=settings.capital_base_url, timeout=_TIMEOUT_SECONDS)
        self._cst: str | None = None
        self._security_token: str | None = None
        self._login_inflight: asyncio.Task[httpx.Response] | None = None
        self._gate = RateGate(_REQUESTS_PER_SECOND)

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def authenticated(self) -> bool:
        return bool(self._cst and self._security_token)

    @property
    def base_url(self) -> str:
        """The host this client is actually bound to — what `capabilities()` names the
        environment from, rather than a constant that cannot come out any other way."""
        return self._s.capital_base_url

    def stream_tokens(self) -> tuple[str, str]:
        """The pair the streaming protocol needs *inside* each message. The stream cannot
        authenticate itself, which is why the streaming half is not a separate credential."""
        if not self.authenticated:
            raise RuntimeError("no capital.com session yet — call login() first")
        return self._cst or "", self._security_token or ""

    async def login(self) -> httpx.Response:
        """Log in, or join the login already running. A stampede costs one request each against
        the account's 10/s budget; a Task rather than a lock hands every waiter the same result."""
        if self._login_inflight is None or self._login_inflight.done():
            self._login_inflight = asyncio.create_task(self._login())
        # Shielded so one caller's cancellation does not cancel the login the others
        # are waiting on.
        return await asyncio.shield(self._login_inflight)

    async def pace(self) -> None:
        """A slot in the provider's budget for a request this client does not send itself —
        the stream's subscribe frames, which capital.com counts like any REST call."""
        await self._gate.acquire()

    async def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Every request to capital.com goes through here, and so through the gate.
        A login counts against the budget like any other call."""
        await self._gate.acquire()
        return await self._http.request(method, path, **kwargs)

    async def _login(self) -> httpx.Response:
        resp = await self._send(
            "POST",
            f"{API_PREFIX}/session",
            headers={"X-CAP-API-KEY": self._s.capital_api_key},
            json={
                "identifier": self._s.capital_identifier,
                "password": self._s.capital_password,
                "encryptedPassword": False,
            },
        )
        if resp.status_code == 200:
            self._cst = resp.headers.get("CST")
            self._security_token = resp.headers.get("X-SECURITY-TOKEN")
        return resp

    def _headers(self) -> dict[str, str]:
        return {
            "X-CAP-API-KEY": self._s.capital_api_key,
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._security_token or "",
        }

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """An authenticated request. Logs in when there is no session; on a 401, logs in
        once more and retries — that is what an expired session looks like from here."""
        if not self.authenticated:
            await self.login()
        resp = await self._send(method, path, headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            await self.login()
            resp = await self._send(method, path, headers=self._headers(), **kwargs)
        return resp

    async def session_details(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/session")

    async def accounts(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/accounts")

    async def switch_account(self, account_id: str) -> httpx.Response:
        return await self.request("PUT", f"{API_PREFIX}/session", json={"accountId": account_id})

    async def top_up(self, amount: float) -> httpx.Response:
        """Moves the demo account's balance by `amount`, positive or negative. No account in the
        body: capital.com adjusts the session's active one, and a parameter would promise a choice."""
        return await self.request(
            "POST", f"{API_PREFIX}/accounts/topUp", json={"amount": amount}
        )

    async def search_markets(self, search_term: str) -> httpx.Response:
        return await self.request(
            "GET", f"{API_PREFIX}/markets", params={"searchTerm": search_term}
        )

    async def market(self, epic: str) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/markets/{epic}")

    async def market_navigation(self, node_id: str | None = None) -> httpx.Response:
        path = f"{API_PREFIX}/marketnavigation"
        if node_id:
            path = f"{path}/{node_id}"
        return await self.request("GET", path)

    async def prices(
        self,
        epic: str,
        resolution: str,
        limit: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> httpx.Response:
        params: dict[str, str | int] = {"resolution": resolution, "max": limit}
        # Omitted rather than sent empty: the provider reads a blank `from` as a bad
        # window, not as "no window".
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        return await self.request("GET", f"{API_PREFIX}/prices/{epic}", params=params)

    async def positions(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/positions")

    async def create_position(self, body: dict) -> httpx.Response:
        return await self.request("POST", f"{API_PREFIX}/positions", json=body)

    async def close_position(self, deal_id: str) -> httpx.Response:
        return await self.request("DELETE", f"{API_PREFIX}/positions/{deal_id}")

    async def update_position(self, deal_id: str, body: dict) -> httpx.Response:
        return await self.request("PUT", f"{API_PREFIX}/positions/{deal_id}", json=body)

    async def working_orders(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/workingorders")

    async def create_working_order(self, body: dict) -> httpx.Response:
        return await self.request("POST", f"{API_PREFIX}/workingorders", json=body)

    async def delete_working_order(self, deal_id: str) -> httpx.Response:
        return await self.request("DELETE", f"{API_PREFIX}/workingorders/{deal_id}")

    async def confirm(self, deal_reference: str) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/confirms/{deal_reference}")
