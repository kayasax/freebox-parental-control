"""Serve and auto-register the bundled Lovelace card.

The integration ships its own card (www/freebox-parental-card.js) and makes it
available to the front-end so users don't have to install anything else or add a
dashboard resource manually.

Two registration mechanisms are used together for maximum robustness:

* ``add_extra_js_url`` — the documented helper that injects an extra module into
  the front-end bootstrap. This works on most set-ups but has been observed to
  silently no-op on some HA versions / dashboard configurations.
* A **Lovelace resource** entry (storage mode) — the same mechanism HACS uses.
  This is the reliable path: the front-end always loads registered Lovelace
  resources, so the ``custom:freebox-parental-card`` element is defined even
  when ``add_extra_js_url`` does not take effect.

If the dashboards are in YAML mode the resource collection is read-only; in that
case we fall back to ``add_extra_js_url`` only and the user must add the resource
manually (documented in the README).
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
    """Register the static path for the card and expose it to the front-end."""
    if hass.data.get("_freebox_card_registered"):
        return
    hass.data["_freebox_card_registered"] = True

    www_dir = os.path.join(os.path.dirname(__file__), "www")
    card_path = os.path.join(www_dir, CARD_FILENAME)
    url = f"{URL_BASE}/{CARD_FILENAME}"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(url, card_path, False)]
    )

    # Cache-bust with the file mtime so updates are picked up by the browser.
    try:
        version = int(os.path.getmtime(card_path))
    except OSError:
        version = 0
    versioned_url = f"{url}?v={version}"

    # Primary, reliable path: register a Lovelace resource (storage mode).
    registered = await _async_register_lovelace_resource(hass, url, versioned_url)

    # Secondary path: the documented extra-module injection. Harmless if the
    # resource above already loaded the card (the card guards its
    # customElements.define call), and it covers set-ups where the resource
    # collection is unavailable.
    add_extra_js_url(hass, versioned_url)

    _LOGGER.debug(
        "Registered Freebox Parental Control card at %s (lovelace resource: %s)",
        versioned_url,
        registered,
    )


async def _async_register_lovelace_resource(
    hass: HomeAssistant, base_url: str, versioned_url: str
) -> bool:
    """Add/refresh the card in the Lovelace resource collection.

    Returns True when the resource is present after the call. Returns False when
    the collection is unavailable or in YAML (read-only) mode.
    """
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None:
            return False

        # Ensure the collection is loaded before inspecting/mutating it.
        if hasattr(resources, "async_get_info"):
            await resources.async_get_info()

        # YAML-mode resource collections have no backing store and are
        # read-only; async_create_item would raise.
        if getattr(resources, "store", None) is None:
            return False

        for item in resources.async_items():
            item_url = (item.get("url") or "").split("?")[0]
            if item_url == base_url:
                # Already present; refresh the version query so browsers pick up
                # a newer card build after an update.
                if item.get("url") != versioned_url:
                    await resources.async_update_item(
                        item["id"],
                        {"res_type": "module", "url": versioned_url},
                    )
                return True

        await resources.async_create_item(
            {"res_type": "module", "url": versioned_url}
        )
        return True
    except Exception as err:  # noqa: BLE001 - best-effort, never break setup
        _LOGGER.debug("Could not register Lovelace resource: %s", err)
        return False
