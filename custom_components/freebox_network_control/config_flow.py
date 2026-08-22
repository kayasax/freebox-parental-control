"""Config flow for Freebox Network Control (LCD authorization)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector

from .api import FreeboxAuthError, FreeboxClient, FreeboxError
from .const import (
    CONF_APP_TOKEN,
    CONF_CUT,
    CONF_DAYS,
    CONF_ENABLED,
    CONF_HOST,
    CONF_RESTORE,
    CONF_SCHEDULES,
    DEFAULT_HOST,
    DOMAIN,
    WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)

DONE = "__done__"


class FreeboxNetworkControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup: register the app, wait for LCD confirmation."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str = DEFAULT_HOST
        self._client: FreeboxClient | None = None
        self._track_id: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> FreeboxOptionsFlow:
        return FreeboxOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST].rstrip("/")
            # Abort BEFORE registering an app on the Freebox if this box is
            # already configured — otherwise every re-run would create a new
            # app token on the box (which the user then has to clean up).
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            session = async_get_clientsession(self.hass)
            self._client = FreeboxClient(session, self._host)
            try:
                self._track_id = await self._client.request_authorization()
            except FreeboxError as err:
                _LOGGER.error("Freebox authorization request failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_authorize()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=DEFAULT_HOST): str}
            ),
            errors=errors,
        )

    async def async_step_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Poll the Freebox for the LCD approval, then create the entry."""
        assert self._client is not None and self._track_id is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                status = await self._client.authorization_status(self._track_id)
            except FreeboxError as err:
                _LOGGER.error("Freebox authorization status failed: %s", err)
                errors["base"] = "cannot_connect"
                status = "unknown"

            if status == "granted":
                # Validate the freshly granted token by opening a session.
                try:
                    await self._client.open_session()
                except FreeboxAuthError as err:
                    _LOGGER.error("Session with new token failed: %s", err)
                    errors["base"] = "invalid_auth"
                else:
                    # unique_id already set in async_step_user (before app
                    # registration); just create the entry.
                    return self.async_create_entry(
                        title="Freebox Parental Control",
                        data={
                            CONF_HOST: self._host,
                            CONF_APP_TOKEN: self._client.app_token,
                        },
                    )
            elif status == "pending":
                errors["base"] = "awaiting_confirmation"
            else:
                errors["base"] = "authorization_failed"

        return self.async_show_form(
            step_id="authorize",
            errors=errors,
        )


class FreeboxOptionsFlow(OptionsFlow):
    """Per-profile cut schedules, editable from the integration's Configure UI.

    Lives in the integration options so every user finds it via
    Settings -> Devices & Services -> Freebox Parental Control -> Configure,
    instead of a personal dashboard.
    """

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._pid: str | None = None

    def _profiles(self) -> dict[int, dict]:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        return dict(coordinator.data) if coordinator else {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._options:
            # Deep-ish copy so we accumulate edits before saving.
            existing = dict(self.config_entry.options or {})
            self._options = {
                CONF_SCHEDULES: dict(existing.get(CONF_SCHEDULES, {}))
            }

        profiles = self._profiles()
        if user_input is not None:
            choice = user_input["profile"]
            if choice == DONE:
                return self.async_create_entry(title="", data=self._options)
            self._pid = str(choice)
            return await self.async_step_schedule()

        # Build the profile picker, annotated with each profile's schedule state.
        options = []
        for pid, prof in profiles.items():
            sched = self._options[CONF_SCHEDULES].get(str(pid), {})
            if sched.get(CONF_ENABLED):
                label = (
                    f"{prof.get('name')} — {sched.get(CONF_CUT)}→"
                    f"{sched.get(CONF_RESTORE)}"
                )
            else:
                label = f"{prof.get('name')} — (aucune programmation)"
            options.append({"value": str(pid), "label": label})
        options.append({"value": DONE, "label": "✓ Enregistrer et fermer"})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("profile"): selector(
                        {"select": {"options": options, "mode": "list"}}
                    )
                }
            ),
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._pid is not None
        cur = self._options[CONF_SCHEDULES].get(self._pid, {})

        if user_input is not None:
            self._options[CONF_SCHEDULES][self._pid] = {
                CONF_ENABLED: user_input[CONF_ENABLED],
                CONF_CUT: user_input[CONF_CUT],
                CONF_RESTORE: user_input[CONF_RESTORE],
                CONF_DAYS: user_input[CONF_DAYS],
            }
            return await self.async_step_init()

        day_options = [
            {"value": d, "label": lbl}
            for d, lbl in zip(
                WEEKDAYS,
                ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
            )
        ]
        profiles = self._profiles()
        name = (profiles.get(int(self._pid), {}) or {}).get("name", self._pid)

        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLED, default=cur.get(CONF_ENABLED, False)
                    ): selector({"boolean": {}}),
                    vol.Required(
                        CONF_CUT, default=cur.get(CONF_CUT, "21:00:00")
                    ): selector({"time": {}}),
                    vol.Required(
                        CONF_RESTORE, default=cur.get(CONF_RESTORE, "07:00:00")
                    ): selector({"time": {}}),
                    vol.Required(
                        CONF_DAYS,
                        default=cur.get(
                            CONF_DAYS, ["mon", "tue", "wed", "thu", "fri"]
                        ),
                    ): selector(
                        {
                            "select": {
                                "options": day_options,
                                "multiple": True,
                                "mode": "list",
                            }
                        }
                    ),
                }
            ),
            description_placeholders={"profile": name},
        )
