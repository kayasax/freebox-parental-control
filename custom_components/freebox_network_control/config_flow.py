"""Config flow for Freebox Network Control (LCD authorization)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FreeboxAuthError, FreeboxClient, FreeboxError
from .const import CONF_APP_TOKEN, CONF_HOST, DEFAULT_HOST, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FreeboxNetworkControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup: register the app, wait for LCD confirmation."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str = DEFAULT_HOST
        self._client: FreeboxClient | None = None
        self._track_id: str | None = None

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
