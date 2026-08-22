"""DataUpdateCoordinator for Freebox network-control profiles."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FreeboxAuthError,
    FreeboxClient,
    FreeboxError,
    FreeboxRightsError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FreeboxProfilesCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    """Fetch all profiles + their network-control state on a single pass."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FreeboxClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.client = client
        self._names_cache: dict[str, str] = {}

    async def _async_update_data(self) -> dict[int, dict]:
        try:
            profiles = await self.client.profiles()
            # Device-name resolution is best-effort; failures must not break the pass.
            try:
                self._names_cache = await self.client.lan_device_names()
            except FreeboxError as err:
                _LOGGER.debug("LAN name resolution failed: %s", err)
        except FreeboxRightsError as err:
            # Token is valid but missing the "Modification des réglages" right.
            # Retryable (no reauth): succeeds automatically once the user grants
            # it in Freebox OS → Gestion des accès → Applications.
            raise UpdateFailed(
                "Freebox app lacks rights. Enable 'Modification des réglages "
                "de la Freebox' for this app in Freebox OS → Gestion des accès "
                f"→ Applications. ({err})"
            ) from err
        except FreeboxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FreeboxError as err:
            raise UpdateFailed(str(err)) from err

        return {int(p["id"]): p for p in profiles if p.get("id") is not None}

    def device_names_for(self, macs: list[str]) -> list[str]:
        return [self._names_cache.get(m.lower(), m) for m in macs or []]

    def device_details_for(self, profile_id: int) -> list[dict]:
        """Per-device info for a profile: name + online status.

        Uses the rich ``hosts`` array returned by network_control, falling back
        to bare MACs when hosts are unavailable.
        """
        prof = self.data.get(profile_id, {})
        nc = prof.get("network_control") or {}
        hosts = nc.get("hosts") or []
        if hosts:
            details = []
            for h in hosts:
                mac = (h.get("l2ident") or {}).get("id", "")
                details.append(
                    {
                        "name": h.get("primary_name")
                        or self._names_cache.get(mac.lower(), mac),
                        "online": bool(h.get("active") or h.get("reachable")),
                        "mac": mac,
                    }
                )
            return sorted(details, key=lambda d: (not d["online"], d["name"].lower()))
        return [
            {"name": self._names_cache.get(m.lower(), m), "online": False, "mac": m}
            for m in nc.get("macs") or []
        ]
