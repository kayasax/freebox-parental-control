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
    CONF_PROFILE_IDS,
    CONF_RESTORE,
    CONF_SCHEDULES,
    WEEKDAY_LABELS_FR,
    WEEKDAYS,
)


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _coerce_profile_ids(sched: dict) -> list[int]:
    """Return the schedule's target profiles as a list of ints.

    Accepts the canonical ``profile_ids`` list and migrates the older single
    ``profile_id`` field transparently.
    """
    raw = sched.get(CONF_PROFILE_IDS)
    if raw is None and sched.get(CONF_PROFILE_ID) is not None:
        raw = [sched[CONF_PROFILE_ID]]
    ids: list[int] = []
    for pid in raw or []:
        try:
            ids.append(int(pid))
        except (ValueError, TypeError):
            continue
    return ids


def normalize_schedules(options: dict[str, Any] | None) -> list[dict]:
    """Return schedules as a canonical list (each with ``profile_ids``).

    Migrates two legacy shapes: the very old dict-by-profile options, and the
    single ``profile_id`` per schedule.
    """
    raw = (options or {}).get(CONF_SCHEDULES)
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[dict] = []
        for s in raw:
            s = dict(s)
            s[CONF_PROFILE_IDS] = _coerce_profile_ids(s)
            s.pop(CONF_PROFILE_ID, None)
            out.append(s)
        return out
    # Very old dict {"<pid>": {...}} -> list
    migrated: list[dict] = []
    for pid, sched in raw.items():
        migrated.append(
            {
                CONF_ID: new_id(),
                CONF_NAME: "Programmation",
                CONF_PROFILE_IDS: [int(pid)],
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


def schedule_label(sched: dict, profile_names: list[str]) -> str:
    """One-line label for a schedule in the picker list."""
    state = "✅" if sched.get(CONF_ENABLED) else "⏸️"
    name = sched.get(CONF_NAME) or "Programmation"
    cut = (sched.get(CONF_CUT) or "")[:5]
    restore = (sched.get(CONF_RESTORE) or "")[:5]
    who = ", ".join(profile_names) if profile_names else "?"
    return (
        f"{state} {name} — {who} {cut}→{restore} "
        f"({days_summary(sched.get(CONF_DAYS, []))})"
    )
