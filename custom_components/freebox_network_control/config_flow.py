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
    CONF_ID,
    CONF_NAME,
    CONF_PROFILE_ID,
    CONF_PROFILE_IDS,
    CONF_RESTORE,
    CONF_SCHEDULES,
    DEFAULT_HOST,
    DOMAIN,
    WEEKDAY_LABELS_FR,
    WEEKDAYS,
)
from .schedule_util import new_id, normalize_schedules, schedule_label

_LOGGER = logging.getLogger(__name__)

ADD = "__add__"
DONE = "__done__"
DELETE = "__delete__"


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
    """Manage a LIST of named cut schedules (add / edit / delete).

    Lives in the integration options so every user finds it via
    Settings -> Devices & Services -> Freebox Parental Control -> Configure.
    """

    def __init__(self) -> None:
        self._schedules: list[dict] | None = None
        self._editing: str | None = None  # schedule id being edited, or None

    def _profiles(self) -> dict[int, dict]:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        return dict(coordinator.data) if coordinator else {}

    def _profile_name(self, pid: Any) -> str:
        try:
            return (self._profiles().get(int(pid), {}) or {}).get(
                "name", str(pid)
            )
        except (ValueError, TypeError):
            return str(pid)

    def _ensure_loaded(self) -> None:
        if self._schedules is None:
            self._schedules = normalize_schedules(self.config_entry.options)

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title="", data={CONF_SCHEDULES: self._schedules}
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """List existing schedules; let the user add one, edit one, or close."""
        self._ensure_loaded()

        if user_input is not None:
            choice = user_input["choice"]
            if choice == DONE:
                return self._save()
            if choice == ADD:
                self._editing = None
                return await self.async_step_edit()
            # choice is a schedule id to edit
            self._editing = choice
            return await self.async_step_edit()

        options = []
        for sched in self._schedules:
            names = [
                self._profile_name(p)
                for p in (sched.get(CONF_PROFILE_IDS) or [])
            ]
            options.append(
                {
                    "value": sched[CONF_ID],
                    "label": schedule_label(sched, names),
                }
            )
        options.append({"value": ADD, "label": "➕ Ajouter une programmation"})
        options.append({"value": DONE, "label": "✓ Terminer"})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): selector(
                        {"select": {"options": options, "mode": "list"}}
                    )
                }
            ),
        )

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add or edit one schedule (or delete it)."""
        self._ensure_loaded()
        editing = next(
            (s for s in self._schedules if s[CONF_ID] == self._editing), None
        )

        if user_input is not None:
            if user_input.get(DELETE) and editing is not None:
                self._schedules = [
                    s for s in self._schedules if s[CONF_ID] != self._editing
                ]
                return await self.async_step_init()

            data = {
                CONF_ID: self._editing or new_id(),
                CONF_NAME: user_input[CONF_NAME],
                CONF_PROFILE_IDS: [int(p) for p in user_input[CONF_PROFILE_IDS]],
                CONF_ENABLED: user_input[CONF_ENABLED],
                CONF_CUT: user_input[CONF_CUT],
                CONF_RESTORE: user_input[CONF_RESTORE],
                CONF_DAYS: user_input[CONF_DAYS],
            }
            if editing is not None:
                self._schedules = [
                    data if s[CONF_ID] == self._editing else s
                    for s in self._schedules
                ]
            else:
                self._schedules.append(data)
            return await self.async_step_init()

        cur = editing or {}
        profiles = self._profiles()
        profile_options = [
            {"value": str(pid), "label": prof.get("name", str(pid))}
            for pid, prof in profiles.items()
        ]
        default_pids = [str(p) for p in (cur.get(CONF_PROFILE_IDS) or [])]
        day_options = [
            {"value": d, "label": WEEKDAY_LABELS_FR[d]} for d in WEEKDAYS
        ]

        schema = {
            vol.Required(
                CONF_NAME, default=cur.get(CONF_NAME, "Nouvelle programmation")
            ): str,
            vol.Required(CONF_PROFILE_IDS, default=default_pids): selector(
                {
                    "select": {
                        "options": profile_options,
                        "multiple": True,
                        "mode": "list",
                    }
                }
            ),
            vol.Required(
                CONF_ENABLED, default=cur.get(CONF_ENABLED, True)
            ): selector({"boolean": {}}),
            vol.Required(
                CONF_CUT, default=cur.get(CONF_CUT, "21:00:00")
            ): selector({"time": {}}),
            vol.Required(
                CONF_RESTORE, default=cur.get(CONF_RESTORE, "07:00:00")
            ): selector({"time": {}}),
            vol.Required(
                CONF_DAYS,
                default=cur.get(CONF_DAYS, ["mon", "tue", "wed", "thu", "fri"]),
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
        # Offer a delete checkbox only when editing an existing schedule.
        if editing is not None:
            schema[vol.Optional(DELETE, default=False)] = selector(
                {"boolean": {}}
            )

        return self.async_show_form(
            step_id="edit",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": cur.get(CONF_NAME, "nouvelle programmation")
            },
        )
