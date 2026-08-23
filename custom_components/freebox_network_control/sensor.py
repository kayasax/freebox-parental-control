"""Sensor platform: devices assigned to each Freebox profile."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FreeboxConfigEntry
from .const import CONF_SCHEDULES, DOMAIN
from .coordinator import FreeboxProfilesCoordinator
from .schedule_util import normalize_schedules


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        FreeboxProfileDevicesSensor(coordinator, pid) for pid in coordinator.data
    ]
    entities.append(FreeboxSchedulesSensor(coordinator, entry))
    async_add_entities(entities)


class FreeboxProfileDevicesSensor(
    CoordinatorEntity[FreeboxProfilesCoordinator], SensorEntity
):
    """State = number of devices assigned to the profile; attrs list names."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:devices"
    _attr_native_unit_of_measurement = "devices"

    def __init__(
        self, coordinator: FreeboxProfilesCoordinator, profile_id: int
    ) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{profile_id}_devices"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{profile_id}")},
        )

    @property
    def _profile(self) -> dict:
        return self.coordinator.data.get(self._profile_id, {})

    @property
    def name(self) -> str:
        return "Devices"

    @property
    def available(self) -> bool:
        return super().available and self._profile_id in self.coordinator.data

    @property
    def _macs(self) -> list[str]:
        nc = self._profile.get("network_control") or {}
        return nc.get("macs") or []

    @property
    def native_value(self) -> int:
        return len(self._macs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        details = self.coordinator.device_details_for(self._profile_id)
        return {
            "profile_id": self._profile_id,
            "online_count": sum(1 for d in details if d["online"]),
            "devices": [d["name"] for d in details],
            "device_status": details,
            "macs": self._macs,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class FreeboxSchedulesSensor(
    CoordinatorEntity[FreeboxProfilesCoordinator], SensorEntity
):
    """Exposes the cut schedules + profile list for the bundled card.

    State = number of schedules. Attributes carry the full schedules list and
    the profiles (id + name) so the front-end card can render and edit them.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"
    _attr_name = "Schedules"

    def __init__(
        self, coordinator: FreeboxProfilesCoordinator, entry: FreeboxConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_schedules"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_hub")},
            manufacturer="Freebox",
            name="Freebox Parental Control",
        )

    @property
    def native_value(self) -> int:
        return len(normalize_schedules(self._entry.options))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        profiles = [
            {"id": pid, "name": (prof.get("name") or str(pid))}
            for pid, prof in self.coordinator.data.items()
        ]
        return {
            "entry_id": self._entry.entry_id,
            "profiles": profiles,
            CONF_SCHEDULES: normalize_schedules(self._entry.options),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Reflect option changes (schedule edits) immediately.
        self.async_on_remove(
            self._entry.add_update_listener(self._async_entry_updated)
        )

    async def _async_entry_updated(self, hass, entry) -> None:
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
