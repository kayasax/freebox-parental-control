"""Constants for the Freebox Network Control integration."""

from __future__ import annotations

DOMAIN = "freebox_network_control"

# App identity registered on the Freebox (shown on the LCD authorization screen).
APP_ID = "com.kayasax.gaia.freebox_network_control"
APP_NAME = "HA Freebox Network Control"
APP_VERSION = "1.0.0"
DEVICE_NAME = "Home Assistant"

DEFAULT_HOST = "http://mafreebox.freebox.fr"

CONF_HOST = "host"
CONF_APP_TOKEN = "app_token"

# Seconds between profile state refreshes. Kept conservative: the proven pyscript
# hammered the box every 5 min with many synchronous calls and overloaded the VM;
# a single async coordinator pass every 60 s is far lighter.
DEFAULT_SCAN_INTERVAL = 60

HTTP_TIMEOUT = 15
