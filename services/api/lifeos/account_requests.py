"""Explicit owned request tracking; no autonomous-work or transcript claims."""

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_records import AccountRecords
from .assistant_models import AssistantProposal
from .models import AccountPreference, LoginSession
from .recommendations import stable_id
from .request_models import RequestState, RequestUpdate, TrackedRequest
from .secretary_preferences import secretary_preferences

KEY = "assistant_requests"


class AccountRequests(AccountRecords):
    def load(self, db, owner):
        self.authorize(db, owner)
        row = db.get(AccountPreference, (owner, KEY))
        return row, RequestState.model_validate_json(row.payload) if row else RequestState()

    def save(self, db, owner, row, state):
        if row is None:
            row = AccountPreference(account_id=owner, kind=KEY, revision=0)
            db.add(row)
        row.payload = state.model_dump_json()
        row.revision += 1

    def public(self, db, owner, item):
        value = item.model_dump()
        if item.status == "waiting_approval":
            proposal = db.get(AssistantProposal, item.proposal_id) if item.proposal_id else None
            session = db.get(LoginSession, proposal.session_hash) if proposal else None
            if proposal and session and session.account_id == owner and proposal.confirmed_id:
                value["status"] = "done"
                value["followup_at"] = None
            elif (
                not proposal
                or not session
                or session.account_id != owner
                or proposal.expires <= time.time()
            ):
                value["status"] = "waiting_user"
            value["proposal_available"] = bool(
                proposal
                and session
                and session.account_id == owner
                and proposal.expires > time.time()
                and not proposal.confirmed_id
            )
        return value

    def listing(self, owner):
        with Session(self.engine) as db:
            _, state = self.load(db, owner)
            items = [self.public(db, owner, item) for item in state.items]
        return {
            "items": sorted(
                items,
                key=lambda item: (item["status"] == "done", item["created_at"]),
                reverse=False,
            ),
            "limit": 100,
        }

    def get(self, owner, id, session_hash=None):
        with Session(self.engine) as db:
            _, state = self.load(db, owner)
            item = next((item for item in state.items if item.id == id), None)
            if item is None:
                raise LookupError("Request not found")
            value = self.public(db, owner, item)
            if session_hash is not None and value["status"] == "waiting_approval":
                proposal = db.get(AssistantProposal, item.proposal_id)
                if (
                    proposal
                    and proposal.session_hash == session_hash
                    and proposal.kind in ("task", "event", "account_task_plan")
                ):
                    payload = json.loads(proposal.payload)
                    if payload.get("account_id") == owner:
                        value["resume_proposal"] = {
                            "id": proposal.id,
                            "kind": "event"
                            if proposal.kind == "account_task_plan"
                            else proposal.kind,
                            "payload": payload["record"],
                            **(
                                {
                                    "change_from": {
                                        key: payload["replacement"][key] for key in ("start", "end")
                                    }
                                }
                                if payload.get("replacement")
                                else {}
                            ),
                        }
                if "resume_proposal" not in value:
                    value["status"] = "waiting_user"
            return value

    def create(self, owner, notice_id):
        from .account_notices import AccountNotices

        feed = AccountNotices(self.engine).feed(owner)
        notice = next(
            (item for item in feed["items"] + feed["hidden"] if item["id"] == notice_id), None
        )
        if notice is None or notice["kind"] == "request_followup":
            raise LookupError("Source update no longer available")
        now = datetime.now(timezone.utc).isoformat()
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            prior = next(
                (
                    item
                    for item in state.items
                    if item.notice_id == notice_id
                    and self.public(db, owner, item)["status"] != "done"
                ),
                None,
            )
            if prior:
                return self.public(db, owner, prior)
            if len(state.items) >= 100:
                raise ValueError("Request limit; remove old tracking first")
            item = TrackedRequest(
                id=str(uuid4()),
                notice_id=notice_id,
                title=notice["title"][:240],
                course_name=notice.get("course_name", "")[:160],
                origin_kind=notice["kind"],
                origin_ids=notice["source_ids"][:10],
                due=notice.get("due") or notice.get("start"),
                created_at=now,
                updated_at=now,
                followup_at=(
                    int(time.time())
                    + secretary_preferences(db, owner)[0].request_followup_minutes * 60
                )
                if secretary_preferences(db, owner)[0].request_followup_minutes
                else None,
            )
            state.items.append(item)
            self.save(db, owner, row, state)
            db.commit()
            return self.public(db, owner, item)

    def update(self, owner, id, values):
        body = RequestUpdate.model_validate(values)
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            item = next((item for item in state.items if item.id == id), None)
            if item is None:
                raise LookupError("Request not found")
            if item.version != body.version:
                raise ValueError("Request changed; refresh")
            if body.status is not None:
                if item.status == "done" and body.status != "done":
                    item.proposal_ids = []
                item.status = body.status
                item.proposal_id = None
            if body.followup_minutes is not None:
                if item.status == "done" and body.followup_minutes:
                    raise ValueError("Reopen request before following up")
                item.followup_at = (
                    int(time.time()) + body.followup_minutes * 60 if body.followup_minutes else None
                )
            if item.status == "done":
                item.followup_at = None
            item.version += 1
            item.updated_at = datetime.now(timezone.utc).isoformat()
            self.save(db, owner, row, state)
            db.commit()
            return self.public(db, owner, item)

    def delete(self, owner, id, version):
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            item = next((item for item in state.items if item.id == id), None)
            if item is None:
                raise LookupError("Request not found")
            if item.version != version:
                raise ValueError("Request changed; refresh")
            state.items.remove(item)
            self.save(db, owner, row, state)
            db.commit()

    def result(self, owner, id, version, proposal_id):
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            item = next((item for item in state.items if item.id == id), None)
            if not item or item.version != version or item.status == "done":
                return False
            if proposal_id:
                associated = list(
                    dict.fromkeys(
                        [
                            *item.proposal_ids,
                            *([item.proposal_id] if item.proposal_id else []),
                            proposal_id,
                        ]
                    )
                )
                if len(associated) > 20:
                    return False
                item.proposal_ids = associated
                item.status, item.proposal_id = "waiting_approval", proposal_id
            elif not self.public(db, owner, item).get("proposal_available"):
                item.status, item.proposal_id = "waiting_user", None
            item.updated_at = datetime.now(timezone.utc).isoformat()
            item.version += 1
            self.save(db, owner, row, state)
            db.commit()
            return True

    def saved(self, owner, proposal_id):
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            changed = False
            for item in state.items:
                if (
                    item.proposal_id == proposal_id or proposal_id in item.proposal_ids
                ) and item.status != "done":
                    item.status, item.followup_at = "done", None
                    item.updated_at = datetime.now(timezone.utc).isoformat()
                    item.version += 1
                    changed = True
            if changed:
                self.save(db, owner, row, state)
                db.commit()

    def link_task_plan(self, owner, task_id, proposal_id):
        with Session(self.engine) as db:
            begin_academic_write(db)
            row, state = self.load(db, owner)
            changed = False
            complete = True
            for item in state.items:
                if task_id not in item.origin_ids or item.status == "done":
                    continue
                associated = list(dict.fromkeys([*item.proposal_ids, proposal_id]))
                if len(associated) > 20:
                    complete = False
                    continue
                item.proposal_ids, item.proposal_id = associated, proposal_id
                item.status = "waiting_approval"
                item.version += 1
                item.updated_at = datetime.now(timezone.utc).isoformat()
                changed = True
            if changed:
                self.save(db, owner, row, state)
                db.commit()
            return complete

    def context(self, owner, id, version):
        item = self.get(owner, id)
        if item["version"] != version:
            raise ValueError("Request changed; refresh")
        if item["status"] == "done":
            raise ValueError("Reopen request before continuing")
        return {
            key: item[key] for key in ("title", "course_name", "due", "origin_kind", "created_at")
        }

    def candidates(self, owner):
        now = int(time.time())
        return [
            {
                "id": stable_id("request_followup", [item["id"], item["followup_at"]]),
                "kind": "request_followup",
                "request_id": item["id"],
                "title": item["title"],
                "course_name": item["course_name"],
                "target": "dashboard",
                "source_ids": [],
                "priority": 2,
                "order": str(item["followup_at"]),
                "observed_at": item["followup_at"],
            }
            for item in self.listing(owner)["items"]
            if item["status"] != "done"
            and item["followup_at"] is not None
            and item["followup_at"] <= now
        ]
