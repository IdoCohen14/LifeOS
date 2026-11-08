"""Actionable work excludes exam storage links; academic/calendar records stay intact."""

from sqlalchemy import exists

from .academic_models import AcademicItem
from .models import Task


def actionable_tasks():
    return ~exists().where(AcademicItem.task_id == Task.id, AcademicItem.kind == "exam")


def is_actionable_task(task):
    return task is not None and task.academic_kind != "exam"
