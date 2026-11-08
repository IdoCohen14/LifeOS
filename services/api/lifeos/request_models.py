"""Bounded request metadata; transcripts remain in opt-in conversation history."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrackedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    notice_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    course_name: str = Field(default="", max_length=160)
    origin_kind: str = Field(max_length=32)
    origin_ids: list[Annotated[str, Field(max_length=256)]] = Field(
        default_factory=list, max_length=10
    )
    due: str | None = Field(default=None, max_length=80)
    status: Literal["waiting_user", "waiting_approval", "waiting_source", "done"] = "waiting_user"
    proposal_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    proposal_ids: list[Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]] = Field(
        default_factory=list, max_length=20
    )
    followup_at: int | None = Field(default=None, ge=0)
    version: int = Field(default=1, ge=1)
    created_at: str = Field(max_length=50)
    updated_at: str = Field(max_length=50)

    @field_validator("created_at", "updated_at")
    @classmethod
    def instant(cls, value):
        if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("Timestamp requires offset")
        return value

    @field_validator("due")
    @classmethod
    def deadline(cls, value):
        if value is not None:
            if len(value) == 10:
                date.fromisoformat(value)
            else:
                cls.instant(value)
        return value


class RequestState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TrackedRequest] = Field(default_factory=list, max_length=100)


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notice_id: str = Field(min_length=1, max_length=128)


class RequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    status: Literal["waiting_user", "waiting_source", "done"] | None = None
    followup_minutes: Literal[0, 60, 1440] | None = None


class RequestDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
