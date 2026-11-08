"""Explicit user preferences, not inferred personal facts or chat storage."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .models import AccountPreference


class SecretaryPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proactive_enabled: bool = True
    suggestion_snooze_minutes: Literal[60, 1440] = 1440
    request_followup_minutes: Literal[0, 60, 1440] = 0
    reply_style: Literal["brief", "standard"] = "brief"
    push_daily_limit: Literal[0, 3, 6, 10] = 0
    class_reminder_minutes: Literal[0, 10, 15, 30] = 0


def secretary_preferences(db, owner):
    row = db.get(AccountPreference, (owner, "secretary"))
    return SecretaryPreferences.model_validate(
        json.loads(row.payload) if row else {}
    ), row.revision if row else 0
