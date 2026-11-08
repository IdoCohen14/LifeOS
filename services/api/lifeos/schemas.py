from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def instant(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A timezone offset is required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    notes: str = Field(default="", max_length=10000)
    priority: Literal["low", "medium", "high"] = "medium"
    due: str | None = None
    completed: bool = False

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A title is required")
        return value

    @field_validator("due")
    @classmethod
    def valid_due(cls, value):
        if value is None:
            return value
        return date.fromisoformat(value).isoformat() if len(value) == 10 else instant(value)


class TaskOutput(TaskInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: str
    academic_id: str | None = None
    academic_course_id: str | None = None
    academic_kind: Literal["assignment", "exam"] | None = None
    academic_course_name: str | None = None


class EventInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    notes: str = Field(default="", max_length=10000)
    start: str
    end: str
    all_day: bool = False

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        return TaskInput.title_not_blank(value)

    @model_validator(mode="after")
    def times(self):
        if self.all_day:
            self.start = date.fromisoformat(self.start).isoformat()
            self.end = date.fromisoformat(self.end).isoformat()
        else:
            self.start, self.end = instant(self.start), instant(self.end)
        invalid = (
            self.end <= self.start
            if self.all_day
            else datetime.fromisoformat(self.end) <= datetime.fromisoformat(self.start)
        )
        if invalid:
            raise ValueError("End must be after start; all-day end is exclusive")
        return self


class EventOutput(EventInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: str
    source: str = "personal"
    course_id: str | None = None
    academic_id: str | None = None


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(default="", max_length=80)
    language: Literal["he", "en"] = "he"
    theme: Literal["dark", "light", "system"] = "dark"
    timezone: str = Field(default="Asia/Jerusalem", max_length=80)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone") from None
        return value


class SettingsOutput(SettingsPatch):
    model_config = ConfigDict(from_attributes=True)


class PasswordInput(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
