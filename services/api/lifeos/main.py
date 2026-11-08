import hmac
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import BoundedSemaphore, Lock
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .academic import academic_router
from .course_batches import course_batch_router
from .data_lock import runtime_lock
from .db import data_directory, migrate, open_database
from .deployment import DeploymentConfig
from .documents import documents_router
from .google_calendar import GoogleCalendarService
from .google_routes import google_router
from .models import Account, CalendarEvent, LoginSession, Settings, Task
from .schemas import (
    EventInput,
    EventOutput,
    PasswordInput,
    SettingsOutput,
    SettingsPatch,
    TaskInput,
    TaskOutput,
)
from .security import token_hash, verify_password
from .task_scope import actionable_tasks, is_actionable_task
from .timetable_batches import timetable_batch_router


def create_app():
    from .assistant import AssistantService
    from .assistant_routes import assistant_router
    from .briefings import briefing_router
    from .conversation_history import ConversationHistoryService, history_router
    from .gmail import GmailService
    from .gmail_routes import gmail_router
    from .moodle import MoodleService
    from .moodle_routes import moodle_router
    from .notifications import NotificationService, notification_router
    from .planning_preferences import preference_router
    from .recommendations import RecommendationService, recommendation_router
    from .recovery_routes import recovery_router
    from .recurring_events import recurring_router
    from .scheduled_backups import scheduled_backup_router
    from .series_management import series_router
    from .series_rescheduling import rescheduling_router
    from .task_planning import TaskPlanningService, planning_router
    from .web_push import web_push_router
    from .weekly_review import WeeklyReviewService, review_router

    deployment = DeploymentConfig.from_env()
    directory = data_directory()
    account_mode = deployment.server or os.environ.get("LIFEOS_ACCOUNT_MODE") == "1"
    key = os.environ.get("LIFEOS_API_KEY", "")
    if not key:
        raise RuntimeError("LIFEOS_API_KEY is required; use scripts/run.py")
    engine = open_database(directory)
    google = GoogleCalendarService(engine, directory)
    gmail = GmailService(engine, directory)
    moodle = MoodleService(engine, directory)
    assistant = AssistantService(engine, google, moodle)
    conversation_history = ConversationHistoryService(engine)
    recommendations = RecommendationService(engine, None, google, moodle)
    notifications = NotificationService(recommendations)
    attempts = deque()
    attempts_lock = Lock()
    password_slots = BoundedSemaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        with runtime_lock(directory):
            try:
                migrate(engine)
                with Session(engine) as db:
                    if deployment.pilot_owner_id:
                        owner = db.get(Account, deployment.pilot_owner_id)
                        if owner is None or not owner.enabled:
                            raise RuntimeError("Configured pilot owner unavailable; provision offline first")
                    if not account_mode and db.scalar(select(Account.id).limit(1)) is not None:
                        raise RuntimeError("Account data requires LIFEOS_ACCOUNT_MODE=1")
                    if db.get(Settings, 1) is None:
                        db.add(Settings(id=1))
                        db.commit()
                yield
            finally:
                google.http.close()
                gmail.http.close()
                moodle.http.close()
                assistant.http.close()
                engine.dispose()

    app = FastAPI(
        title="LifeOS local API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.google = google
    app.state.gmail = gmail
    app.state.moodle = moodle
    app.state.assistant = assistant
    app.state.recommendations = recommendations

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Default validation details can echo passwords and private request bodies.
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @app.middleware("http")
    async def secure(request: Request, call_next):
        if not hmac.compare_digest(request.headers.get("X-LifeOS-Key", ""), key):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != deployment.origin:
            return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
        if (
            account_mode
            and request.url.path != "/mode"
            and not request.url.path.startswith("/accounts/")
        ):
            return JSONResponse({"detail": "Use account workspace"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.get("/mode")
    def mode():
        return {
            "account_mode": account_mode,
            "registration_open": deployment.pilot_owner_id is None,
            "test_mode": os.environ.get("LIFEOS_TEST_MODE") == "1",
        }

    def database():
        with Session(engine) as db:
            yield db

    def authenticated(request: Request, db: Session = Depends(database)):
        token = request.cookies.get("lifeos_session", "")
        session = db.get(LoginSession, token_hash(token))
        if session is None or session.expires <= int(time.time()):
            raise HTTPException(401, "Session expired; sign in again")
        if session.account_id is not None:
            raise HTTPException(403, "Account workspaces are not activated")
        if request.method not in ("GET", "HEAD"):
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
                raise HTTPException(403, "Invalid CSRF token")
        return session

    @app.post("/session")
    def login(body: PasswordInput, response: Response, db: Session = Depends(database)):
        # Bound memory-intensive password hashing before entering the rate window.
        if not password_slots.acquire(blocking=False):
            raise HTTPException(429, "Sign-in busy; retry shortly", headers={"Retry-After": "1"})
        try:
            with attempts_lock:
                tick = time.monotonic()
                while attempts and attempts[0] <= tick - 60:
                    attempts.popleft()
                if len(attempts) >= 10:
                    raise HTTPException(
                        429, "Too many attempts; wait one minute", headers={"Retry-After": "60"}
                    )
                attempts.append(tick)
            if not verify_password(directory, body.password):
                raise HTTPException(401, "Incorrect password or setup incomplete")
            with attempts_lock:
                attempts.clear()
        finally:
            password_slots.release()
        now = time.time()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute(delete(LoginSession).where(LoginSession.expires <= int(now)))
        db.add(LoginSession(token_hash=token_hash(token), csrf=csrf, expires=int(now) + 43200))
        db.commit()
        response.set_cookie(
            "lifeos_session", token, httponly=True, samesite="strict", max_age=43200, path="/"
        )
        return {"csrf": csrf}

    @app.get("/session")
    def session_info(session=Depends(authenticated)):
        return {"csrf": session.csrf, "test_mode": os.environ.get("LIFEOS_TEST_MODE") == "1"}

    @app.delete("/session", status_code=204)
    def logout(response: Response, session=Depends(authenticated), db: Session = Depends(database)):
        db.delete(session)
        db.commit()
        response.delete_cookie("lifeos_session", path="/")

    def find(db, model, record_id):
        obj = db.get(model, record_id)
        if obj is None:
            raise HTTPException(404, "Record not found")
        return obj

    @app.get("/tasks", response_model=list[TaskOutput], dependencies=[Depends(authenticated)])
    def tasks(db: Session = Depends(database)):
        return db.scalars(select(Task).where(actionable_tasks()).order_by(Task.created_at.desc())).all()

    @app.post(
        "/tasks", response_model=TaskOutput, status_code=201, dependencies=[Depends(authenticated)]
    )
    def add_task(body: TaskInput, db: Session = Depends(database)):
        task = Task(
            id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat(), **body.model_dump()
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @app.put("/tasks/{record_id}", response_model=TaskOutput, dependencies=[Depends(authenticated)])
    def update_task(record_id: str, body: TaskInput, db: Session = Depends(database)):
        task = find(db, Task, record_id)
        if not is_actionable_task(task):
            raise HTTPException(404, "Task unavailable")
        if task.academic_item and any(
            getattr(task, key) != value
            for key, value in body.model_dump().items()
            if key != "completed"
        ):
            raise HTTPException(409, "Edit linked academic tasks in their course workspace")
        for field, value in body.model_dump().items():
            setattr(task, field, value)
        db.commit()
        db.refresh(task)
        return task

    @app.delete("/tasks/{record_id}", status_code=204, dependencies=[Depends(authenticated)])
    def delete_task(record_id: str, db: Session = Depends(database)):
        task = find(db, Task, record_id)
        if not is_actionable_task(task):
            raise HTTPException(404, "Task unavailable")
        if task.academic_item:
            raise HTTPException(409, "Delete linked academic tasks in their course workspace")
        db.delete(task)
        db.commit()

    @app.get("/events", response_model=list[EventOutput], dependencies=[Depends(authenticated)])
    def events(db: Session = Depends(database)):
        return db.scalars(select(CalendarEvent).order_by(CalendarEvent.start)).all()

    @app.post(
        "/events",
        response_model=EventOutput,
        status_code=201,
        dependencies=[Depends(authenticated)],
    )
    def add_event(body: EventInput, db: Session = Depends(database)):
        event = CalendarEvent(
            id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat(), **body.model_dump()
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @app.put(
        "/events/{record_id}", response_model=EventOutput, dependencies=[Depends(authenticated)]
    )
    def update_event(record_id: str, body: EventInput, db: Session = Depends(database)):
        event = find(db, CalendarEvent, record_id)
        for field, value in body.model_dump().items():
            setattr(event, field, value)
        db.commit()
        db.refresh(event)
        return event

    @app.delete("/events/{record_id}", status_code=204, dependencies=[Depends(authenticated)])
    def delete_event(record_id: str, db: Session = Depends(database)):
        db.delete(find(db, CalendarEvent, record_id))
        db.commit()

    @app.get("/settings", response_model=SettingsOutput, dependencies=[Depends(authenticated)])
    def settings(db: Session = Depends(database)):
        return db.get(Settings, 1)

    @app.put("/settings", response_model=SettingsOutput, dependencies=[Depends(authenticated)])
    def update_settings(body: SettingsPatch, db: Session = Depends(database)):
        settings = db.get(Settings, 1)
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(settings, field, value)
        db.commit()
        db.refresh(settings)
        return settings

    app.include_router(academic_router(database, authenticated))
    app.include_router(course_batch_router(database, authenticated))
    app.include_router(timetable_batch_router(database, authenticated))
    app.include_router(documents_router(database, authenticated))
    app.include_router(google_router(google, authenticated, gmail))
    app.include_router(gmail_router(gmail, authenticated))
    app.include_router(moodle_router(moodle, authenticated))
    app.include_router(assistant_router(assistant, authenticated, conversation_history))
    app.include_router(history_router(conversation_history, authenticated))
    app.include_router(recommendation_router(recommendations, authenticated))
    app.include_router(notification_router(notifications, authenticated))
    app.include_router(briefing_router(notifications.briefings, authenticated))
    app.include_router(planning_router(TaskPlanningService(engine), authenticated))
    app.include_router(series_router(engine, authenticated))
    app.include_router(rescheduling_router(engine, authenticated))
    app.include_router(recurring_router(engine, authenticated))
    app.include_router(preference_router(engine, authenticated))
    app.include_router(review_router(WeeklyReviewService(engine), authenticated))
    app.include_router(web_push_router(engine, directory, authenticated))
    app.include_router(scheduled_backup_router(engine, directory, authenticated))
    app.include_router(recovery_router(directory, authenticated))
    from .account_routes import account_router

    app.include_router(
        account_router(engine, directory, enabled=account_mode, shared_assistant=assistant)
    )
    return app
