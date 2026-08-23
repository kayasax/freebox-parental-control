"""Built-in scheduler: cut/restore profiles at configured times.

Reads per-profile schedules from ``entry.options`` and registers wall-clock
listeners (async_track_time_change). At each cut time (on the selected
weekdays) it denies the profile's Internet; at each restore time it clears the
override. This runs entirely inside the integration — no automations or
blueprints required — so it is discoverable and portable for every user.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .api import FreeboxError
from .const import (
    CONF_CUT,
    CONF_DAYS,
    CONF_ENABLED,
    CONF_PROFILE_IDS,
    CONF_RESTORE,
    WEEKDAYS,
)
from .coordinator import FreeboxProfilesCoordinator
from .schedule_util import normalize_schedules

_LOGGER = logging.getLogger(__name__)


def _parse_hms(value: str) -> tuple[int, int, int]:
    parts = (value or "0:0:0").split(":")
    parts += ["0"] * (3 - len(parts))
    return int(parts[0]), int(parts[1]), int(parts[2])


class FreeboxScheduler:
    """Owns the time listeners for one config entry's schedules."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: FreeboxProfilesCoordinator,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._unsubs: list[callable] = []

    @callback
    def async_setup(self) -> None:
        """(Re)register all listeners from the current options."""
        self.async_unload()
        for sched in normalize_schedules(self._entry.options):
            if not sched.get(CONF_ENABLED):
                continue
            for pid in sched.get(CONF_PROFILE_IDS) or []:
                self._register(int(pid), sched)

    def _register(self, pid: int, sched: dict) -> None:
        days = sched.get(CONF_DAYS) or WEEKDAYS
        cut_h, cut_m, cut_s = _parse_hms(sched.get(CONF_CUT, ""))
        res_h, res_m, res_s = _parse_hms(sched.get(CONF_RESTORE, ""))

        @callback
        def _at_cut(now: datetime, _pid: int = pid, _days: list = days) -> None:
            if WEEKDAYS[now.weekday()] in _days:
                self._hass.async_create_task(self._apply(_pid, cut=True))

        @callback
        def _at_restore(now: datetime, _pid: int = pid) -> None:
            # Restore always runs regardless of weekday so Internet is never
            # left cut (e.g. a cut that spans midnight into a non-selected day).
            self._hass.async_create_task(self._apply(_pid, cut=False))

        self._unsubs.append(
            async_track_time_change(
                self._hass, _at_cut, hour=cut_h, minute=cut_m, second=cut_s
            )
        )
        self._unsubs.append(
            async_track_time_change(
                self._hass, _at_restore, hour=res_h, minute=res_m, second=res_s
            )
        )

    async def _apply(self, pid: int, cut: bool) -> None:
        client = self._coordinator.client
        try:
            if cut:
                await client.set_override(pid, "denied")
            else:
                await client.clear_override(pid)
            await self._coordinator.async_request_refresh()
            _LOGGER.info(
                "Scheduled %s applied to profile %s",
                "cut" if cut else "restore",
                pid,
            )
        except FreeboxError as err:
            _LOGGER.error(
                "Scheduled %s for profile %s failed: %s",
                "cut" if cut else "restore",
                pid,
                err,
            )

    @callback
    def async_unload(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()
