"""Switch platform: one switch per Freebox profile (cut/restore Internet)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FreeboxConfigEntry
from .const import DOMAIN
from .coordinator import FreeboxProfilesCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_CUT_FOR = "cut_for"
SERVICE_ALLOW_FOR = "allow_for"
_MINUTES_SCHEMA = {
    vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440))
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        FreeboxProfileSwitch(coordinator, pid) for pid in coordinator.data
    )

    # Entity service: cut a profile's Internet for a bounded number of minutes,
    # with automatic restore (Freebox override_until).
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_CUT_FOR, _MINUTES_SCHEMA, "async_cut_for"
    )
    # Mirror service: temporarily ALLOW Internet (e.g. during a scheduled cut),
    # the Freebox itself reverts to the schedule once override_until expires.
    platform.async_register_entity_service(
        SERVICE_ALLOW_FOR, _MINUTES_SCHEMA, "async_allow_for"
    )


class FreeboxProfileSwitch(
    CoordinatorEntity[FreeboxProfilesCoordinator], SwitchEntity
):
    """Switch is ON when the profile currently has Internet access."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:web"

    def __init__(
        self, coordinator: FreeboxProfilesCoordinator, profile_id: int
    ) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{profile_id}_internet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{profile_id}")},
            manufacturer="Freebox",
            model="Network Control Profile",
            name=self._profile_name,
        )

    @property
    def _profile(self) -> dict:
        return self.coordinator.data.get(self._profile_id, {})

    @property
    def _profile_name(self) -> str:
        return self._profile.get("name") or f"Profile {self._profile_id}"

    @property
    def name(self) -> str:
        return "Internet"

    @property
    def available(self) -> bool:
        return super().available and self._profile_id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        """True = Internet allowed for this profile right now."""
        nc = self._profile.get("network_control") or {}
        return nc.get("current_mode", "allowed") != "denied"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nc = self._profile.get("network_control") or {}
        macs = nc.get("macs") or []
        return {
            "profile_id": self._profile_id,
            "override": nc.get("override"),
            "override_mode": nc.get("override_mode"),
            "override_until": nc.get("override_until"),
            "devices": self.coordinator.device_names_for(macs),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Restore Internet for this profile."""
        await self.coordinator.client.clear_override(self._profile_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cut Internet for this profile."""
        await self.coordinator.client.set_override(self._profile_id, "denied")
        await self.coordinator.async_request_refresh()

    async def async_cut_for(self, minutes: int) -> None:
        """Cut Internet for a bounded duration, then auto-restore."""
        await self.coordinator.client.set_override(
            self._profile_id, "denied", minutes
        )
        await self.coordinator.async_request_refresh()

    async def async_allow_for(self, minutes: int) -> None:
        """Allow Internet for a bounded duration, then back to the schedule."""
        await self.coordinator.client.set_override(
            self._profile_id, "allowed", minutes
        )
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
