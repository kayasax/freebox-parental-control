"""Async client for the local Freebox OS API (network-control / profiles).

Ported from the proven synchronous ``scripts/freebox_bridge.py`` client to
aiohttp so it can run inside the Home Assistant event loop. Only the local LAN
API is used; nothing goes through the cloud.

Discovery is resilient to DNS quirks: ``mafreebox.freebox.fr`` can resolve to
Free's public portal IP (212.27.38.x) instead of the box when an external
resolver answers, so :meth:`FreeboxClient.discover` probes several candidate
hosts (the configured host, the box's default LAN gateway, then the mDNS name)
and locks onto the first that returns a valid ``api_version`` payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

import aiohttp

from .const import (
    APP_ID,
    APP_NAME,
    APP_VERSION,
    DEVICE_NAME,
    HTTP_TIMEOUT,
    LOCAL_GATEWAY,
    DEFAULT_MDNS_HOST,
)

_LOGGER = logging.getLogger(__name__)


class FreeboxError(Exception):
    """A Freebox API call failed or returned success=false."""


class FreeboxAuthError(FreeboxError):
    """App token is invalid/revoked — fatal, requires re-authorization."""


class FreeboxSessionExpired(FreeboxError):
    """The session token expired (auth_required). Retryable via re-login."""


class FreeboxRightsError(FreeboxError):
    """The app token is valid but lacks the required Freebox settings rights.

    Fixed by the user enabling "Modification des réglages de la Freebox" in
    Freebox OS → Gestion des accès → Applications. Retryable: no re-auth needed.
    """


class FreeboxClient:
    """Minimal async Freebox OS client for profiles + network_control."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        app_token: str = "",
    ) -> None:
        self._session = session
        self._host = host.rstrip("/")
        self._app_token = app_token
        self._base = ""
        self._session_token = ""

    @property
    def app_token(self) -> str:
        return self._app_token

    # ---- low-level HTTP ----------------------------------------------------
    async def _request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        allow_reauth: bool = True,
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._session_token:
            headers["X-Fbx-App-Auth"] = self._session_token
        try:
            async with self._session.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise FreeboxError(
                f"Cannot reach Freebox at {url}: {exc}. "
                "Home Assistant must be on the same LAN as the Freebox."
            ) from exc
        if isinstance(body, dict) and body.get("success") is False:
            code = body.get("error_code", "error")
            msg = body.get("msg", "unknown error")
            if code == "insufficient_rights":
                raise FreeboxRightsError(f"{code}: {msg}")
            if code == "invalid_token":
                raise FreeboxAuthError(f"{code}: {msg}")
            if code == "auth_required":
                # Session token expired. Transparently re-login once and retry,
                # unless this IS a login call (avoid recursion) or we already
                # retried.
                if allow_reauth and self._app_token and "/login" not in url:
                    self._session_token = ""
                    await self.open_session()
                    return await self._request(
                        method, url, payload, allow_reauth=False
                    )
                raise FreeboxSessionExpired(f"{code}: {msg}")
            raise FreeboxError(f"{code}: {msg}")
        return body

    # ---- discovery ---------------------------------------------------------
    async def discover(self) -> None:
        """Locate a reachable Freebox and build the versioned API base URL.

        ``mafreebox.freebox.fr`` is *not* reliable: depending on which DNS
        resolver answers, it can resolve to Free's public portal IP
        (212.27.38.x) instead of the box on the LAN, which breaks every call.
        We therefore probe a list of candidate hosts and lock onto the first
        one that actually returns a valid Freebox ``api_version`` payload,
        prioritising the box's stable LAN gateway address.
        """
        candidates: list[str] = []
        for host in (self._host, LOCAL_GATEWAY, DEFAULT_MDNS_HOST):
            h = (host or "").rstrip("/")
            if h and h not in candidates:
                candidates.append(h)

        last_exc: Exception | None = None
        for host in candidates:
            try:
                info = await self._request("GET", f"{host}/api_version")
                if not (
                    isinstance(info, dict)
                    and "api_base_url" in info
                    and "api_version" in info
                ):
                    raise FreeboxError(
                        f"{host} did not return a Freebox api_version payload"
                    )
                api_base = info["api_base_url"].strip("/")
                major = "v" + str(info["api_version"]).split(".")[0]
            except Exception as exc:  # noqa: BLE001 - try next candidate
                last_exc = exc
                _LOGGER.debug("Freebox not reachable at %s: %s", host, exc)
                continue
            self._host = host
            self._base = f"{self._host}/{api_base}/{major}"
            _LOGGER.info("Freebox API reachable at %s", self._host)
            return
        raise last_exc or FreeboxError(
            "No Freebox reachable among candidates: " + ", ".join(candidates)
        )

    async def _ensure_base(self) -> None:
        if not self._base:
            await self.discover()

    # ---- authorization (one-time, LCD confirmation) ------------------------
    async def request_authorization(self) -> str:
        """Register the app and return the track_id to poll for LCD approval."""
        await self._ensure_base()
        resp = await self._request(
            "POST",
            f"{self._base}/login/authorize/",
            {
                "app_id": APP_ID,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_name": DEVICE_NAME,
            },
        )
        result = resp["result"]
        self._app_token = result["app_token"]
        return result["track_id"]

    async def authorization_status(self, track_id: str) -> str:
        """Return 'pending' | 'granted' | 'denied' | 'timeout' | 'unknown'."""
        await self._ensure_base()
        resp = await self._request(
            "GET", f"{self._base}/login/authorize/{track_id}"
        )
        return resp["result"]["status"]

    # ---- session -----------------------------------------------------------
    async def open_session(self) -> None:
        await self._ensure_base()
        if not self._app_token:
            raise FreeboxAuthError("No app_token; authorize first.")
        challenge = (await self._request("GET", f"{self._base}/login/"))[
            "result"
        ]["challenge"]
        password = hmac.new(
            self._app_token.encode(), challenge.encode(), hashlib.sha1
        ).hexdigest()
        resp = await self._request(
            "POST",
            f"{self._base}/login/session/",
            {"app_id": APP_ID, "app_version": APP_VERSION, "password": password},
        )
        self._session_token = resp["result"]["session_token"]

    async def _ensure_session(self) -> None:
        if not self._session_token:
            await self.open_session()

    # ---- profiles / network control ---------------------------------------
    async def profiles(self) -> list[dict]:
        """List network-control profiles enriched with their live state."""
        await self._ensure_session()
        profs = (await self._request("GET", f"{self._base}/profile/")).get(
            "result"
        ) or []
        enriched: list[dict] = []
        for prof in profs:
            pid = prof.get("id")
            try:
                state = await self.network_control(pid)
            except FreeboxError:
                state = {}
            enriched.append({**prof, "network_control": state})
        return enriched

    async def network_control(self, profile_id: int) -> dict:
        await self._ensure_session()
        return (
            await self._request(
                "GET", f"{self._base}/network_control/{profile_id}"
            )
        ).get("result") or {}

    async def set_override(
        self, profile_id: int, mode: str, minutes: int = 0
    ) -> dict:
        """Force a profile's Internet mode. mode = 'denied' (cut) or 'allowed'."""
        await self._ensure_session()
        cur = await self.network_control(profile_id)
        until = 0
        if minutes > 0:
            import time

            until = int(time.time()) + minutes * 60
        payload = {
            "profile_id": profile_id,
            "macs": cur.get("macs") or [],
            "cdayranges": cur.get("cdayranges") or [],
            "override": True,
            "override_mode": mode,
            "override_until": until,
        }
        resp = await self._request(
            "PUT", f"{self._base}/network_control/{profile_id}", payload
        )
        return resp.get("result") or {}

    async def clear_override(self, profile_id: int) -> dict:
        await self._ensure_session()
        cur = await self.network_control(profile_id)
        payload = {
            "profile_id": profile_id,
            "macs": cur.get("macs") or [],
            "cdayranges": cur.get("cdayranges") or [],
            "override": False,
            "override_mode": cur.get("override_mode") or "allowed",
            "override_until": 0,
        }
        resp = await self._request(
            "PUT", f"{self._base}/network_control/{profile_id}", payload
        )
        return resp.get("result") or {}

    async def lan_device_names(self) -> dict[str, str]:
        """Map lowercased MAC -> friendly device name across all interfaces."""
        await self._ensure_session()
        names: dict[str, str] = {}
        interfaces = (
            await self._request("GET", f"{self._base}/lan/browser/interfaces/")
        ).get("result") or []
        for itf in interfaces:
            name = itf.get("name")
            if not name:
                continue
            hosts = (
                await self._request("GET", f"{self._base}/lan/browser/{name}/")
            ).get("result") or []
            for host in hosts:
                mac = (host.get("l2ident") or {}).get("id")
                if mac:
                    names[mac.lower()] = host.get("primary_name") or mac
        return names
