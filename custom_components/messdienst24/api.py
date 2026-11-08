"""Minimal client for the legacy messdienst24.de tenant portal (HTML only)."""

from __future__ import annotations

import aiohttp

from .const import BASE_URL
from .parsing import Meter, parse_meters

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


class Messdienst24Error(Exception):
    """Base error."""


class Messdienst24AuthError(Messdienst24Error):
    """Username or password rejected."""


class Messdienst24ConnectionError(Messdienst24Error):
    """Portal not reachable or returned something unexpected."""


class Messdienst24Client:
    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str, md: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._md = md

    async def _request(self, method: str, path: str, **kwargs) -> str:
        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                headers=_HEADERS,
                timeout=_TIMEOUT,
                **kwargs,
            ) as resp:
                resp.raise_for_status()
                return (await resp.read()).decode("utf-8", "replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Messdienst24ConnectionError(str(err)) from err

    async def async_login(self) -> None:
        self._session.cookie_jar.clear()
        # 1) session cookie, 2) accept privacy notice (required before login),
        # 3) login - the portal itself sends the credentials as GET parameters.
        await self._request("GET", "/", params={"md": self._md})
        await self._request(
            "GET", "/", params={"action": "", "node": "content", "acceptds": "1"}
        )
        page = await self._request(
            "GET",
            "/index.htm",
            params={
                "action": "",
                "node": "page",
                "username": self._username,
                "password": self._password,
            },
        )
        if "login_dialog" in page or "nicht korrekt" in page:
            raise Messdienst24AuthError("Login rejected")
        if "logout" not in page:
            raise Messdienst24ConnectionError("Unexpected response after login")

    async def async_get_meters(self) -> list[Meter]:
        await self.async_login()
        page = await self._request(
            "POST", "/", data={"action": "objverbmiet", "node": "content"}
        )
        return parse_meters(page)
