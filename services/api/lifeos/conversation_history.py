"""Optional actual conversation text. Never verified memory or replayable actions."""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .conversation_models import AssistantHistoryPreferences, ConversationTurn
from .models import LoginSession

MAX_TURNS = 200
LOAD_TURNS = 50


def current_time():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class HistoryPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ConversationHistoryService:
    def __init__(self, engine):
        self.engine = engine

    def state(self, db):
        row = db.get(AssistantHistoryPreferences, 1)
        return {"enabled": bool(row and row.enabled), "generation": row.generation if row else 0}

    def history(self):
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            state = self.state(db)
            cutoff = stamp(current_time() - timedelta(days=30))
            count = db.scalar(select(func.count()).select_from(ConversationTurn))
            available = db.scalar(
                select(func.count())
                .select_from(ConversationTurn)
                .where(ConversationTurn.created_at >= cutoff)
            )
            rows = (
                list(
                    db.scalars(
                        select(ConversationTurn)
                        .where(ConversationTurn.created_at >= cutoff)
                        .order_by(ConversationTurn.id.desc())
                        .limit(LOAD_TURNS)
                    )
                )
                if state["enabled"]
                else []
            )
            messages = [
                {
                    "id": f"{row.turn_id}:{role}",
                    "role": role,
                    "text": value,
                    "created_at": row.created_at,
                }
                for row in reversed(rows)
                for role, value in [("user", row.user_text), ("assistant", row.assistant_text)]
            ]
            return {
                **state,
                "stored_count": count,
                "available_turns": available,
                "truncated": available > LOAD_TURNS,
                "messages": messages,
            }

    def configure(self, enabled):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(AssistantHistoryPreferences, 1)
            if row is None:
                db.add(AssistantHistoryPreferences(id=1, enabled=enabled, generation=1))
            elif row.enabled != enabled:
                row.enabled, row.generation = enabled, row.generation + 1
            db.commit()
        return self.history()

    def clear(self):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(AssistantHistoryPreferences, 1)
            if row is None:
                db.add(AssistantHistoryPreferences(id=1, enabled=False, generation=1))
            else:
                row.generation += 1
            db.execute(delete(ConversationTurn))
            db.commit()
        return self.history()

    def prune(self):
        with Session(self.engine) as db:
            db.execute(
                delete(ConversationTurn).where(
                    ConversationTurn.created_at < stamp(current_time() - timedelta(days=30))
                )
            )
            db.commit()

    def record(self, turn_id, message, reply, generation, session_hash):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            state = self.state(db)
            session = db.get(LoginSession, session_hash)
            if (
                not state["enabled"]
                or state["generation"] != generation
                or not session
                or session.expires <= time.time()
            ):
                return "discarded", None
            now = current_time()
            db.execute(
                delete(ConversationTurn).where(
                    ConversationTurn.created_at < stamp(now - timedelta(days=30))
                )
            )
            prior = db.scalar(select(ConversationTurn).where(ConversationTurn.turn_id == turn_id))
            if prior:
                if prior.user_text != message:
                    raise HTTPException(409, "history_turn_changed")
                return "replayed", prior.assistant_text
            db.add(
                ConversationTurn(
                    turn_id=turn_id, user_text=message, assistant_text=reply, created_at=stamp(now)
                )
            )
            db.flush()
            retained = (
                select(ConversationTurn.id).order_by(ConversationTurn.id.desc()).limit(MAX_TURNS)
            )
            db.execute(delete(ConversationTurn).where(ConversationTurn.id.not_in(retained)))
            db.commit()
        return "saved", None

    def chat(self, service, body, session_hash):
        turn_id = body.turn_id or str(uuid4())
        initial = {"enabled": False, "generation": body.history_generation or 0}
        mismatch = False
        read_error = False
        try:
            with Session(self.engine) as db:
                db.execute(text("BEGIN"))
                initial = self.state(db)
                mismatch = (body.history_generation or 0) != initial["generation"]
                if mismatch:
                    body = type(body).model_validate(
                        {**body.model_dump(), "history": [], "ephemeral": True}
                    )
                if initial["enabled"] and not body.ephemeral:
                    cutoff = stamp(current_time() - timedelta(days=30))
                    prior = db.scalar(
                        select(ConversationTurn).where(
                            ConversationTurn.turn_id == turn_id,
                            ConversationTurn.created_at >= cutoff,
                        )
                    )
                    if prior:
                        if prior.user_text != body.message:
                            raise HTTPException(409, "history_turn_changed")
                        return {
                            "reply": prior.assistant_text,
                            "proposal": None,
                            "history_replayed": True,
                            "history_saved": True,
                            "history_state": initial,
                        }
                    rows = list(
                        db.scalars(
                            select(ConversationTurn)
                            .where(ConversationTurn.created_at >= cutoff)
                            .order_by(ConversationTurn.id.desc())
                            .limit(3)
                        )
                    )
                    context = [
                        {"role": role, "content": value[:600]}
                        for row in reversed(rows)
                        for role, value in [
                            ("user", row.user_text),
                            ("assistant", row.assistant_text),
                        ]
                    ]
                    body = type(body).model_validate({**body.model_dump(), "history": context})
                elif (body.history_generation or 0) != initial["generation"]:
                    body = type(body).model_validate({**body.model_dump(), "history": []})
        except SQLAlchemyError:
            read_error = True
            body = type(body).model_validate(
                {**body.model_dump(), "history": [], "ephemeral": True}
            )
        result = service.chat(body, session_hash)
        result = {**result, "history_saved": False}
        if mismatch or read_error:
            result["history_discarded"] = True
        if read_error:
            result["history_error"] = True
        if initial["enabled"] and not body.ephemeral:
            reply = result.get("reply")
            try:
                if not isinstance(reply, str) or len(reply) > 2000:
                    raise ValueError("history_reply_limit")
                outcome, old_reply = self.record(
                    turn_id, body.message, reply, initial["generation"], session_hash
                )
                result["history_saved"] = outcome in ("saved", "replayed")
                if outcome == "discarded":
                    result["history_discarded"] = True
                elif outcome == "replayed":
                    result.update(reply=old_reply, proposal=None, history_replayed=True)
            except (SQLAlchemyError, ValueError):
                result["history_error"] = True
        try:
            with Session(self.engine) as db:
                result["history_state"] = self.state(db)
                if result["history_state"]["generation"] != initial["generation"]:
                    result["history_discarded"] = True
        except SQLAlchemyError:
            result["history_state"] = initial
            result["history_error"] = True
        return result


def history_router(service, authenticated):
    router = APIRouter(prefix="/assistant/history", dependencies=[Depends(authenticated)])

    @router.get("")
    def history():
        return service.history()

    @router.put("")
    def configure(body: HistoryPreference):
        return service.configure(body.enabled)

    @router.delete("")
    def clear():
        return service.clear()

    return router
