"""Helpers for schedule options (list model + legacy migration)."""

from __future__ import annotations

import uuid
from typing import Any

from .const import (
    CONF_CUT,
    CONF_DAYS,
    CONF_ENABLED,
    CONF_ID,
    CONF_NAME,
    CONF_PROFILE_ID,
    CONF_RESTORE,
    CONF_SCHEDULES,
    WEEKDAY_LABELS_FR,
    WEEKDAYS,
)


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def normalize_schedules(options: dict[str, Any] | None) -> list[dict]:
    """Return schedules as a list, migrating the legacy dict-by-profile shape.

    Legacy: options[CONF_SCHEDULES] = {"<pid>": {enabled,cut,restore,days}}
    New:    options[CONF_SCHEDULES] = [ {id,name,profile_id,enabled,...}, ... ]
    """
    raw = (options or {}).get(CONF_SCHEDULES)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [dict(s) for s in raw]
    # Legacy dict -> list
    migrated: list[dict] = []
    for pid, sched in raw.items():
        migrated.append(
            {
                CONF_ID: new_id(),
                CONF_NAME: "Programmation",
                CONF_PROFILE_ID: int(pid),
                CONF_ENABLED: sched.get(CONF_ENABLED, False),
                CONF_CUT: sched.get(CONF_CUT, "21:00:00"),
                CONF_RESTORE: sched.get(CONF_RESTORE, "07:00:00"),
                CONF_DAYS: sched.get(CONF_DAYS, list(WEEKDAYS)),
            }
        )
    return migrated


def days_summary(days: list[str]) -> str:
    """Human-friendly day summary (FR)."""
    days = [d for d in WEEKDAYS if d in (days or [])]
    if not days:
        return "aucun jour"
    if days == WEEKDAYS:
        return "tous les jours"
    if days == ["mon", "tue", "wed", "thu", "fri"]:
        return "en semaine"
    if days == ["sat", "sun"]:
        return "le week-end"
    return ", ".join(WEEKDAY_LABELS_FR[d][:3] for d in days)


def schedule_label(sched: dict, profile_name: str) -> str:
    """One-line label for a schedule in the picker list."""
    state = "✅" if sched.get(CONF_ENABLED) else "⏸️"
    name = sched.get(CONF_NAME) or "Programmation"
    cut = (sched.get(CONF_CUT) or "")[:5]
    restore = (sched.get(CONF_RESTORE) or "")[:5]
    return (
        f"{state} {name} — {profile_name} {cut}→{restore} "
        f"({days_summary(sched.get(CONF_DAYS, []))})"
    )
