"""Serve and auto-register the bundled Lovelace card.

The integration ships its own card (www/freebox-parental-card.js) and injects
it into the front-end, so users don't have to install anything else or add a
dashboard resource manually.
"""

from __future__ import annotations

import logging
import os

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/freebox_parental_control"
CARD_FILENAME = "freebox-parental-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register the static path for the card and inject it once."""
    if hass.data.get("_freebox_card_registered"):
        return
    hass.data["_freebox_card_registered"] = True

    www_dir = os.path.join(os.path.dirname(__file__), "www")
    card_path = os.path.join(www_dir, CARD_FILENAME)
    url = f"{URL_BASE}/{CARD_FILENAME}"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(url, card_path, False)]
    )
    # Cache-bust with the file mtime so updates are picked up.
    try:
        version = int(os.path.getmtime(card_path))
    except OSError:
        version = 0
    add_extra_js_url(hass, f"{url}?v={version}")
    _LOGGER.debug("Registered Freebox Parental Control card at %s", url)
