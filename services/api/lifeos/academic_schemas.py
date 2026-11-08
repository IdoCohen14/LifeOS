from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import SettingsPatch, TaskInput


class AcademicBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, allow_inf_nan=False)


class TermInput(AcademicBase):
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates(self):
        days = (self.end_date - self.start_date).days
        if not 0 <= days <= 366:
            raise ValueError("Term must span 0 to 366 days")
        return self


class TermOutput(TermInput):
    id: str


class CourseFields(AcademicBase):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=50)
    instructor: str = Field(default="", max_length=120)
    credits: float = Field(default=0, ge=0, le=60)
    color: str = Field(default="#a597ff", pattern=r"^#[0-9a-fA-F]{6}$")


class CourseInput(CourseFields):
    term_id: str


class CourseOutput(CourseInput):
    id: str


class ItemInput(AcademicBase):
    course_id: str
    title: str = Field(min_length=1, max_length=240)
    notes: str = Field(default="", max_length=10000)
    kind: Literal["assignment", "exam"] = "assignment"
    due: str
    effort_hours: float = Field(default=0, ge=0, le=1000)
    duration_minutes: int = Field(default=120, ge=1, le=720)
    completed: bool = False

    @field_validator("due")
    @classmethod
    def due_valid(cls, value):
        return TaskInput.valid_due(value)


class ItemOutput(ItemInput):
    id: str
    task_id: str


class SlotFields(AcademicBase):
    course_id: str
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = "Asia/Jerusalem"
    location: str = Field(default="", max_length=240)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        return SettingsPatch.valid_zone(value)

    @model_validator(mode="after")
    def times(self):
        if time.fromisoformat(self.end_time) <= time.fromisoformat(self.start_time):
            raise ValueError("End time must be after start time on the same day")
        return self


class SlotInput(SlotFields):
    weekday: int = Field(ge=0, le=6)


class SlotOutput(SlotInput):
    id: str


class GradeInput(AcademicBase):
    course_id: str
    title: str = Field(min_length=1, max_length=240)
    score: float = Field(ge=0)
    maximum: float = Field(default=100, gt=0, le=100000)
    weight: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def score_valid(self):
        if self.score > self.maximum:
            raise ValueError("Score cannot exceed maximum")
        return self


class GradeOutput(GradeInput):
    id: str
