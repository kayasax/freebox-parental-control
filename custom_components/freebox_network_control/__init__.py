"""The Freebox Network Control integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FreeboxClient
from .const import CONF_APP_TOKEN, CONF_HOST, DEFAULT_HOST, DOMAIN
from .coordinator import FreeboxProfilesCoordinator
from .scheduler import FreeboxScheduler

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

# ConfigEntry subscripted with runtime_data type (PEP 695 `type` alias needs
# Python 3.12; a plain alias keeps the code importable on older interpreters
# used for linting/CI while still working on HA's 3.12+ runtime).
FreeboxConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: FreeboxConfigEntry) -> bool:
    """Set up Freebox Network Control from a config entry."""
    session = async_get_clientsession(hass)
    client = FreeboxClient(
        session,
        entry.data.get(CONF_HOST, DEFAULT_HOST),
        entry.data[CONF_APP_TOKEN],
    )
    coordinator = FreeboxProfilesCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Built-in scheduler driven by entry.options (per-profile cut schedules).
    scheduler = FreeboxScheduler(hass, entry, coordinator)
    scheduler.async_setup()
    entry.async_on_unload(scheduler.async_unload)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = scheduler
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: FreeboxConfigEntry
) -> None:
    """Re-arm the scheduler when the user edits schedules in the options UI."""
    scheduler: FreeboxScheduler | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if scheduler is not None:
        scheduler.async_setup()


async def async_unload_entry(hass: HomeAssistant, entry: FreeboxConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
