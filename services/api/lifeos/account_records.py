"""Internal owned manual records. Not wired to legacy global routes/services."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_reads import ReadBudget
from .deployment import DeploymentConfig
from .models import Account, CalendarEvent, Task
from .schemas import EventInput, EventOutput, TaskInput, TaskOutput
from .task_scope import actionable_tasks, is_actionable_task

KINDS = {"tasks": (Task, TaskInput, TaskOutput), "events": (CalendarEvent, EventInput, EventOutput)}


class AccountRecords:
    def __init__(self, engine):
        self.engine = engine

    def authorize(self, db, account_id):
        if not DeploymentConfig.from_env().allows_account(account_id):
            raise PermissionError("Account unavailable")
        account = db.get(Account, account_id)
        if account is None or not account.enabled:
            raise PermissionError("Account unavailable")

    def list(self, account_id, kind):
        model, _, output = KINDS[kind]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            query = select(model).where(model.account_id == account_id)
            if kind == "tasks":
                query = query.where(actionable_tasks())
            return [
                output.model_validate(row).model_dump()
                for row in ReadBudget().collect(
                    db.scalars(
                        query.limit(10001)
                    ).yield_per(200)
                )
            ]

    def save(self, account_id, kind, body, record_id=None):
        model, schema, output = KINDS[kind]
        values = schema.model_validate(body).model_dump()
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            if record_id is None:
                row = model(
                    id=str(uuid4()),
                    account_id=account_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    **values,
                )
                db.add(row)
            else:
                row = db.scalar(
                    select(model).where(model.id == record_id, model.account_id == account_id)
                )
                if row is None:
                    raise LookupError("Record not found")
                if model is Task and not is_actionable_task(row):
                    raise LookupError("Task unavailable")
                if model is Task and row.academic_id:
                    if any(getattr(row, key) != value for key, value in values.items()
                           if key != "completed"):
                        raise ValueError("Edit academic tasks through their academic record")
                for key, value in values.items():
                    setattr(row, key, value)
            db.flush()
            result = output.model_validate(row).model_dump()
            db.commit()
            return result

    def delete(self, account_id, kind, record_id):
        model, _, _ = KINDS[kind]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row = db.scalar(
                select(model).where(model.id == record_id, model.account_id == account_id)
            )
            if row is None:
                raise LookupError("Record not found")
            if model is Task and not is_actionable_task(row):
                raise LookupError("Task unavailable")
            if model is Task and row.academic_id:
                raise ValueError("Delete academic tasks through their academic record")
            db.delete(row)
            db.commit()
