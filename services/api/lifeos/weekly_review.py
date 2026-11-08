"""Read-only status-marking review with explicit tracking/retention limits."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import Account, AccountPreference, Settings, Task
from .schemas import SettingsPatch
from .task_history_models import TaskHistoryMetadata, TaskStatusHistory
from .task_scope import actionable_tasks

MAX_HISTORY = 20000
MAX_TASKS = 100000
MAX_SECONDS = 10


def current_time():
    return datetime.now(timezone.utc)


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def utc_text(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class WeeklyReviewService:
    def __init__(self, engine):
        self.engine = engine

    def review(self, end=None, *, account_id=None):
        now = current_time()
        deadline = time.monotonic() + MAX_SECONDS

        def budget(count, maximum):
            if count > maximum or time.monotonic() > deadline:
                raise HTTPException(503, "review_resource_limit")

        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            account = None
            if account_id is not None:
                account = db.get(Account, account_id)
                if account is None or not account.enabled:
                    raise PermissionError("Account unavailable")
                pref = db.get(AccountPreference, (account_id, "settings"))
                zone_name = SettingsPatch.model_validate(
                    json.loads(pref.payload) if pref else {}
                ).timezone
            else:
                zone_name = db.get(Settings, 1).timezone
            zone = ZoneInfo(zone_name)
            today = now.astimezone(zone).date()
            try:
                last = date.fromisoformat(end) if end else today
            except ValueError:
                raise HTTPException(422, "review_date_range") from None
            if not today - timedelta(days=83) <= last <= today:
                raise HTTPException(422, "review_date_range")
            first, after = last - timedelta(days=6), last + timedelta(days=1)
            left = datetime.combine(first, datetime.min.time(), zone).astimezone(timezone.utc)
            right = datetime.combine(after, datetime.min.time(), zone).astimezone(timezone.utc)
            tracking = (
                account.created_at
                if account
                else db.get(TaskHistoryMetadata, 1).tracking_started_at
            )
            if account:
                prior_tracking = db.get(AccountPreference, (account_id, "review_tracking"))
                if prior_tracking:
                    tracking = json.loads(prior_tracking.payload)["tracking_started_at"]
            tracked = instant(tracking)
            available_from = max(tracked, now - timedelta(days=90))
            daily = {}
            for offset in range(7):
                day = first + timedelta(days=offset)
                begin = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
                finish = datetime.combine(
                    day + timedelta(days=1), datetime.min.time(), zone
                ).astimezone(timezone.utc)
                daily[day.isoformat()] = {
                    "day": day.isoformat(),
                    "available": finish > available_from,
                    "partial": begin < available_from < finish,
                    "completed": set(),
                    "reopened": set(),
                }
            completed, reopened = {}, set()
            transition_count = 0
            rows = db.execute(
                select(TaskStatusHistory, Task.title, Task.completed)
                .join(Task, Task.id == TaskStatusHistory.task_id)
                .where(
                    Task.account_id == account_id, actionable_tasks(),
                    TaskStatusHistory.occurred_at >= utc_text(max(left, available_from)),
                    TaskStatusHistory.occurred_at < utc_text(right),
                )
                .order_by(TaskStatusHistory.occurred_at)
                .execution_options(yield_per=500)
            )
            for index, (row, title, current) in enumerate(rows, 1):
                budget(index, MAX_HISTORY)
                transition_count += 1
                day = instant(row.occurred_at).astimezone(zone).date().isoformat()
                if row.completed:
                    completed[row.task_id] = {
                        "task_id": row.task_id,
                        "title": title,
                        "completed_at": row.occurred_at,
                        "currently_completed": current,
                    }
                    daily[day]["completed"].add(row.task_id)
                else:
                    reopened.add(row.task_id)
                    daily[day]["reopened"].add(row.task_id)
            open_count = db.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.account_id == account_id, actionable_tasks(), Task.completed.is_(False))
            )
            unknown = db.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.account_id == account_id, actionable_tasks(),
                    Task.completed.is_(True),
                    ~select(TaskStatusHistory.id)
                    .where(
                        TaskStatusHistory.task_id == Task.id, TaskStatusHistory.completed.is_(True)
                    )
                    .exists(),
                )
            )
            overdue = 0
            for index, due in enumerate(
                db.scalars(
                    select(Task.due)
                    .where(
                        Task.account_id == account_id, actionable_tasks(),
                        Task.completed.is_(False),
                        Task.due.is_not(None),
                    )
                    .execution_options(yield_per=500)
                ),
                1,
            ):
                budget(index, MAX_TASKS)
                overdue += date.fromisoformat(due) < today if len(due) == 10 else instant(due) < now
            budget(0, MAX_HISTORY)
            return {
                "range_start": first.isoformat(),
                "range_end": after.isoformat(),
                "today": today.isoformat(),
                "earliest_end": (today - timedelta(days=83)).isoformat(),
                "timezone": zone_name,
                "as_of": utc_text(now),
                "tracking_started_at": tracking,
                "available_from": utc_text(available_from),
                "completed": len(completed),
                "reopened": len(reopened),
                "transition_count": transition_count,
                "open_now": open_count,
                "overdue_now": overdue,
                "unknown_completed": unknown,
                "days": [
                    {**row, "completed": len(row["completed"]), "reopened": len(row["reopened"])}
                    for row in daily.values()
                ],
                "recent": sorted(
                    completed.values(), key=lambda row: row["completed_at"], reverse=True
                )[:10],
                "recent_truncated": len(completed) > 10,
            }


def review_router(service, authenticated):
    router = APIRouter(prefix="/review", dependencies=[Depends(authenticated)])

    @router.get("/academic")
    def academic():
        from .academic_review import academic_snapshot

        return academic_snapshot(service.engine)

    @router.get("/weekly")
    def weekly(end: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return service.review(end)

    return router
