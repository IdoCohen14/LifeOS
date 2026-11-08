"""Explicit user-selected defaults, separate from assistant text and source records."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import JSON, Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base

DEFAULTS = {
    "enabled": False,
    "assistant_enabled": False,
    "duration": 30,
    "daily_limit_minutes": None,
    "days": 1,
    "window_start": "08:00",
    "window_end": "20:00",
    "weekdays": list(range(1, 8)),
}
Weekdays = Annotated[
    list[Annotated[int, Field(strict=True, ge=1, le=7)]], Field(min_length=1, max_length=7)
]


def normalize_weekdays(value):
    if value is not None and len(value) != len(set(value)):
        raise ValueError("duplicate_weekdays")
    return sorted(value) if value is not None else None


CLOCK = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


class PlanningPreferences(Base):
    __tablename__ = "planning_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=30)
    days: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[str] = mapped_column(String(5), default="08:00")
    window_end: Mapped[str] = mapped_column(String(5), default="20:00")
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=lambda: list(range(1, 8)))


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0, le=2147483647)


class PreferenceInput(Revision):
    weekdays: Weekdays | None = None

    @field_validator("weekdays")
    @classmethod
    def weekdays_valid(cls, value):
        if value is None:
            raise ValueError("weekdays_required")
        return normalize_weekdays(value)

    enabled: bool
    assistant_enabled: bool = False
    daily_limit_minutes: int | None = Field(default=None, ge=15, le=1440, multiple_of=15)
    duration: int = Field(ge=5, le=240, multiple_of=5)
    days: int = Field(ge=1, le=7)
    window_start: str = Field(pattern=CLOCK)
    window_end: str = Field(pattern=CLOCK)

    @model_validator(mode="after")
    def valid_window(self):
        def minutes(value):
            hours, minutes = map(int, value.split(":"))
            return hours * 60 + minutes

        if minutes(self.window_end) - minutes(self.window_start) < self.duration:
            raise ValueError("planning_preference_window")
        return self


def snapshot(row):
    return (
        {**{key: getattr(row, key) for key in DEFAULTS}, "revision": row.revision}
        if row
        else {**DEFAULTS, "weekdays": list(DEFAULTS["weekdays"]), "revision": 0}
    )


class PlanningPreferenceService:
    def __init__(self, engine):
        self.engine = engine

    def get(self):
        with Session(self.engine) as db:
            return snapshot(db.get(PlanningPreferences, 1))

    def save(self, revision, values):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(PlanningPreferences, 1)
            if revision != (row.revision if row else 0):
                raise HTTPException(409, "planning_preferences_changed")
            if row is None:
                row = PlanningPreferences(id=1)
                db.add(row)
            for key, value in values.items():
                setattr(row, key, value)
            row.revision = revision + 1
            db.flush()
            result = snapshot(row)
            db.commit()
            return result


def preference_router(engine, authenticated):
    service = PlanningPreferenceService(engine)
    router = APIRouter(prefix="/planning/preferences", dependencies=[Depends(authenticated)])

    @router.get("")
    def get():
        return service.get()

    @router.put("")
    def save(body: PreferenceInput):
        values = body.model_dump(exclude={"revision"}, exclude_none=True)
        if "daily_limit_minutes" in body.model_fields_set:
            values["daily_limit_minutes"] = body.daily_limit_minutes
        return service.save(body.revision, values)

    @router.delete("")
    def clear(body: Revision):
        return service.save(body.revision, DEFAULTS)

    return router
