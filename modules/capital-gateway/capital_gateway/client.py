"""Thin async client for the capital.com REST API.

Low-level on purpose: every method hands back the raw ``httpx.Response``. Turning a
payload into a DTO happens one layer up, in the adapter, so the two failure modes —
"the provider said no" and "the provider said something we did not expect" — stay
separable.

What it does own is the session. capital.com authenticates statefully: ``POST /session``
answers with ``CST`` and ``X-SECURITY-TOKEN`` as response *headers*, good for about ten
idle minutes. Callers never see them.
"""

from __future__ import annotations

import httpx

from .config import Settings

API_PREFIX = "/api/v1"
_TIMEOUT_SECONDS = 20.0


class CapitalClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.capital_base_url, timeout=_TIMEOUT_SECONDS
        )
        self._cst: str | None = None
        self._security_token: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def authenticated(self) -> bool:
        return bool(self._cst and self._security_token)

    def stream_tokens(self) -> tuple[str, str]:
        """The pair the streaming protocol needs *inside* each message.

        The stream cannot authenticate itself — it takes the tokens this client already
        holds, which is why the streaming half is not a separate credential.
        """
        if not self.authenticated:
            raise RuntimeError("no capital.com session yet — call login() first")
        return self._cst or "", self._security_token or ""

    async def login(self) -> httpx.Response:
        resp = await self._http.post(
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
        resp = await self._http.request(method, path, headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            await self.login()
            resp = await self._http.request(method, path, headers=self._headers(), **kwargs)
        return resp

    # --- convenience wrappers, all returning the raw response ---

    async def session_details(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/session")

    async def accounts(self) -> httpx.Response:
        return await self.request("GET", f"{API_PREFIX}/accounts")

    async def switch_account(self, account_id: str) -> httpx.Response:
        return await self.request("PUT", f"{API_PREFIX}/session", json={"accountId": account_id})

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
