"""Services to manage cut schedules from the front-end card.

The bundled Lovelace card reads schedules from the schedules sensor attribute
and mutates them through these services, so the whole experience lives on the
dashboard without going through the integration options screen.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CUT,
    CONF_DAYS,
    CONF_ENABLED,
    CONF_ID,
    CONF_NAME,
    CONF_PROFILE_ID,
    CONF_RESTORE,
    CONF_SCHEDULES,
    DOMAIN,
    WEEKDAYS,
)
from .schedule_util import new_id, normalize_schedules

SERVICE_SCHEDULE_UPSERT = "schedule_upsert"
SERVICE_SCHEDULE_DELETE = "schedule_delete"

_UPSERT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional(CONF_ID): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PROFILE_ID): vol.Coerce(int),
        vol.Optional(CONF_ENABLED, default=True): cv.boolean,
        vol.Required(CONF_CUT): cv.string,
        vol.Required(CONF_RESTORE): cv.string,
        vol.Required(CONF_DAYS): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
    }
)

_DELETE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Required(CONF_ID): cv.string,
    }
)


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry | None:
    """Pick the target config entry (explicit entry_id, else the only one)."""
    entry_id = call.data.get("entry_id")
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        return next((e for e in entries if e.entry_id == entry_id), None)
    loaded = [e for e in entries if e.state.recoverable or True]
    return loaded[0] if loaded else None


def _normalize_hms(value: str) -> str:
    parts = (value or "0:0:0").split(":")
    parts += ["0"] * (3 - len(parts))
    return ":".join(f"{int(p):02d}" for p in parts[:3])


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the schedule management services (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_SCHEDULE_UPSERT):
        return

    async def _upsert(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call)
        if entry is None:
            return
        schedules = normalize_schedules(entry.options)
        sched = {
            CONF_ID: call.data.get(CONF_ID) or new_id(),
            CONF_NAME: call.data[CONF_NAME],
            CONF_PROFILE_ID: int(call.data[CONF_PROFILE_ID]),
            CONF_ENABLED: call.data[CONF_ENABLED],
            CONF_CUT: _normalize_hms(call.data[CONF_CUT]),
            CONF_RESTORE: _normalize_hms(call.data[CONF_RESTORE]),
            CONF_DAYS: list(call.data[CONF_DAYS]),
        }
        existing = next(
            (i for i, s in enumerate(schedules) if s[CONF_ID] == sched[CONF_ID]),
            None,
        )
        if existing is not None:
            schedules[existing] = sched
        else:
            schedules.append(sched)
        hass.config_entries.async_update_entry(
            entry, options={**dict(entry.options), CONF_SCHEDULES: schedules}
        )

    async def _delete(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call)
        if entry is None:
            return
        target = call.data[CONF_ID]
        schedules = [
            s for s in normalize_schedules(entry.options) if s[CONF_ID] != target
        ]
        hass.config_entries.async_update_entry(
            entry, options={**dict(entry.options), CONF_SCHEDULES: schedules}
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SCHEDULE_UPSERT, _upsert, schema=_UPSERT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SCHEDULE_DELETE, _delete, schema=_DELETE_SCHEMA
    )
