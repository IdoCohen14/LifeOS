"""Opt-in account conversation text with bounded retention and context reset."""

import json
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_records import AccountRecords
from .assistant import session_scope
from .models import AccountConversationTurn, AccountPreference


class TurnInput(BaseModel):
    user_text: str = Field(min_length=1, max_length=4000)
    reply_text: str = Field(min_length=1, max_length=16000)


class AccountConversation(AccountRecords):
    def state(self, db, account_id):
        pref = db.get(AccountPreference, (account_id, "history"))
        context = db.get(AccountPreference, (account_id, "history_context"))
        return {
            "enabled": bool(pref and json.loads(pref.payload).get("enabled")),
            "generation": (pref.revision if pref else 0) + (context.revision if context else 0),
        }

    def history(self, account_id):
        rows = self.list(account_id)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            state = self.state(db, account_id)
        return {
            **state,
            "stored_count": len(rows),
            "available_turns": len(rows),
            "truncated": len(rows) == 50,
            "messages": [
                {
                    "id": row["id"] + ":" + role,
                    "role": role,
                    "text": value,
                    "created_at": row["created_at"],
                }
                for row in rows
                for role, value in (("user", row["user_text"]), ("assistant", row["reply_text"]))
            ],
        }

    def prune(self, db, account_id):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        db.execute(
            delete(AccountConversationTurn).where(
                AccountConversationTurn.account_id == account_id,
                AccountConversationTurn.created_at < cutoff,
            )
        )
        keep = (
            select(AccountConversationTurn.id)
            .where(AccountConversationTurn.account_id == account_id)
            .order_by(AccountConversationTurn.created_at.desc(), AccountConversationTurn.id.desc())
            .limit(200)
        )
        db.execute(
            delete(AccountConversationTurn).where(
                AccountConversationTurn.account_id == account_id,
                AccountConversationTurn.id.not_in(keep),
            )
        )

    def append(
        self,
        account_id,
        user_text,
        reply_text,
        *,
        turn_id=None,
        generation=None,
        session_hash=None,
        return_record=False,
    ):
        body = TurnInput(user_text=user_text, reply_text=reply_text)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            if session_hash is not None:
                session_scope(db, session_hash, account_id)
            state = self.state(db, account_id)
            if generation is not None and state["generation"] != generation:
                return None if return_record else False
            pref = db.get(AccountPreference, (account_id, "history"))
            if pref is None or json.loads(pref.payload).get("enabled") is not True:
                return None if return_record else False
            id = str(uuid5(NAMESPACE_URL, account_id + ":" + turn_id)) if turn_id else str(uuid4())
            prior = db.get(AccountConversationTurn, id)
            if prior:
                if prior.account_id != account_id or prior.user_text != user_text:
                    raise ValueError("History turn changed")
                return {"replayed": True, "reply": prior.reply_text} if return_record else True
            db.add(
                AccountConversationTurn(
                    id=id,
                    account_id=account_id,
                    user_text=body.user_text,
                    reply_text=body.reply_text,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    include_context=True,
                )
            )
            db.flush()
            self.prune(db, account_id)
            db.commit()
            return {"replayed": False, "reply": reply_text} if return_record else True

    def list(self, account_id, *, context_only=False):
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            self.prune(db, account_id)
            query = select(AccountConversationTurn).where(
                AccountConversationTurn.account_id == account_id
            )
            if context_only:
                pref = db.get(AccountPreference, (account_id, "history"))
                if pref is None or json.loads(pref.payload).get("enabled") is not True:
                    db.commit()
                    return []
                query = query.where(AccountConversationTurn.include_context.is_(True))
            rows = list(
                db.scalars(
                    query.order_by(
                        AccountConversationTurn.created_at.desc(), AccountConversationTurn.id.desc()
                    ).limit(50)
                )
            )
            result = [
                {
                    "id": row.id,
                    "user_text": row.user_text,
                    "reply_text": row.reply_text,
                    "created_at": row.created_at,
                }
                for row in reversed(rows)
            ]
            db.commit()
            return result

    def clear(self, account_id, *, context_only=False):
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            context = db.get(AccountPreference, (account_id, "history_context"))
            if context is None:
                context = AccountPreference(
                    account_id=account_id, kind="history_context", revision=0, payload="{}"
                )
                db.add(context)
            context.revision += 1
            if context_only:
                db.execute(
                    update(AccountConversationTurn)
                    .where(AccountConversationTurn.account_id == account_id)
                    .values(include_context=False)
                )
            else:
                db.execute(
                    delete(AccountConversationTurn).where(
                        AccountConversationTurn.account_id == account_id
                    )
                )
            db.commit()

    def chat(self, account_id, service, body, session_hash):
        turn_id = body.turn_id or str(uuid4())
        with Session(self.engine) as db:
            session_scope(db, session_hash, account_id)
            initial = self.state(db, account_id)
        mismatch = (body.history_generation or 0) != initial["generation"]
        if mismatch:
            body = type(body).model_validate(
                {**body.model_dump(), "history": [], "ephemeral": True}
            )
        if initial["enabled"] and not body.ephemeral:
            id = str(uuid5(NAMESPACE_URL, account_id + ":" + turn_id))
            with Session(self.engine) as db:
                session_scope(db, session_hash, account_id)
                prior = db.get(AccountConversationTurn, id)
                if (
                    prior
                    and prior.created_at
                    >= (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
                ):
                    if prior.account_id != account_id or prior.user_text != body.message:
                        raise ValueError("History turn changed")
                    return {
                        "reply": prior.reply_text,
                        "proposal": None,
                        "history_replayed": True,
                        "history_saved": True,
                        "history_state": initial,
                    }
            rows = self.list(account_id, context_only=True)[-3:]
            context = [
                {"role": role, "content": value[:600]}
                for row in rows
                for role, value in (("user", row["user_text"]), ("assistant", row["reply_text"]))
            ]
            body = type(body).model_validate({**body.model_dump(), "history": context})
        result = {**service.chat(body, session_hash), "history_saved": False}
        if mismatch:
            result["history_discarded"] = True
        if initial["enabled"] and not body.ephemeral:
            saved = self.append(
                account_id,
                body.message,
                result["reply"],
                turn_id=turn_id,
                generation=initial["generation"],
                session_hash=session_hash,
                return_record=True,
            )
            result["history_saved"] = saved is not None
            if saved is None:
                result["history_discarded"] = True
            elif saved["replayed"]:
                result.update(reply=saved["reply"], proposal=None, history_replayed=True)
        with Session(self.engine) as db:
            session_scope(db, session_hash, account_id)
            result["history_state"] = self.state(db, account_id)
        if result["history_state"]["generation"] != initial["generation"]:
            result["history_discarded"] = True
        return result
