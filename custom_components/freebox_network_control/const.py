"""Constants for the Freebox Network Control integration."""

from __future__ import annotations

DOMAIN = "freebox_network_control"

# App identity registered on the Freebox (shown on the LCD authorization screen).
# NOTE: the Freebox rejects app_id longer than ~32 chars ("app_id is too long"),
# so keep this short.
APP_ID = "com.kayasax.freebox_parental"
APP_NAME = "HA Freebox Parental Control"
APP_VERSION = "1.0.0"
DEVICE_NAME = "Home Assistant"

DEFAULT_HOST = "http://mafreebox.freebox.fr"

CONF_HOST = "host"
CONF_APP_TOKEN = "app_token"

# Options (entry.options) — per-profile cut schedules.
# CONF_SCHEDULES is a LIST of schedule objects (multiple per profile allowed):
#   { CONF_ID: "<uuid>", CONF_NAME: "Semaine", CONF_PROFILE_ID: 3,
#     CONF_ENABLED: true, CONF_CUT: "HH:MM:SS", CONF_RESTORE: "HH:MM:SS",
#     CONF_DAYS: ["mon", ...] }
# (Legacy shape was a dict keyed by profile_id with one schedule each; it is
# migrated to this list transparently — see util.normalize_schedules.)
CONF_SCHEDULES = "schedules"
CONF_ID = "id"
CONF_NAME = "name"
CONF_PROFILE_ID = "profile_id"
CONF_PROFILE_IDS = "profile_ids"
CONF_ENABLED = "enabled"
CONF_CUT = "cut"
CONF_RESTORE = "restore"
CONF_DAYS = "days"

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_LABELS_FR = {
    "mon": "Lundi",
    "tue": "Mardi",
    "wed": "Mercredi",
    "thu": "Jeudi",
    "fri": "Vendredi",
    "sat": "Samedi",
    "sun": "Dimanche",
}

# Seconds between profile state refreshes. Kept conservative: the proven pyscript
# hammered the box every 5 min with many synchronous calls and overloaded the VM;
# a single async coordinator pass every 60 s is far lighter.
DEFAULT_SCAN_INTERVAL = 60

HTTP_TIMEOUT = 15
