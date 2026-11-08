"""Workspace HTTP adapters; ownership always comes from the authenticated context."""

from urllib.parse import quote

from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .academic_calendar import iter_calendar
from .academic_models import Course, StudyDocument, Term
from .academic_reads import ReadBudget
from .academic_review import academic_snapshot
from .account_academic import AccountAcademic
from .account_batches import AccountBatches
from .account_briefings import AccountBriefings
from .account_conversation import AccountConversation
from .account_notices import AccountNotices
from .account_planning import AccountPlanning
from .account_preferences import AccountPreferences
from .account_requests import AccountRequests
from .assistant import AssistantService, ChatInput
from .assistant_help import catalog
from .assistant_models import AssistantProposal
from .assistant_routes import Confirmation
from .documents import DocumentInput
from .models import AccountBriefing
from .proactive_planning import ProactivePlanning
from .recurring_events import RecurringEventService, RecurringInput
from .request_models import RequestCreate, RequestDelete, RequestUpdate
from .series_management import DeleteInput, SeriesManagementService
from .series_rescheduling import RescheduleInput, SeriesReschedulingService
from .weekly_review import WeeklyReviewService


def bind_workspace(router, engine, directory, authenticated, shared_assistant):
    academic, prefs = AccountAcademic(engine), AccountPreferences(engine)
    history, notices = AccountConversation(engine), AccountNotices(engine)
    planning, batches = AccountPlanning(engine), AccountBatches(engine)
    briefings = AccountBriefings(engine)
    requests = AccountRequests(engine)

    @router.get("/assistant/requests")
    def request_list(context=Depends(authenticated)):
        return requests.listing(context.id)

    @router.post("/assistant/requests", status_code=201)
    def request_create(body: RequestCreate, context=Depends(authenticated)):
        return requests.create(context.id, body.notice_id)

    @router.get("/assistant/requests/{id}")
    def request_get(id: str, context=Depends(authenticated)):
        return requests.get(context.id, id, context.session_hash)

    @router.patch("/assistant/requests/{id}")
    def request_update(id: str, body: RequestUpdate, context=Depends(authenticated)):
        return requests.update(context.id, id, body.model_dump(exclude_none=True))

    @router.delete("/assistant/requests/{id}", status_code=204)
    def request_delete(id: str, body: RequestDelete, context=Depends(authenticated)):
        requests.delete(context.id, id, body.version)

    @router.get("/academic/calendar")
    def academic_calendar(context=Depends(authenticated)):
        budget = ReadBudget()
        with Session(engine) as db:
            academic.authorize(db, context.id)
            return sorted(
                budget.collect(iter_calendar(db, budget.check, account_id=context.id)),
                key=lambda row: row["start"],
            )

    @router.get("/academic/documents")
    def documents(context=Depends(authenticated)):
        with Session(engine) as db:
            academic.authorize(db, context.id)
            query = (
                select(
                    StudyDocument.id,
                    StudyDocument.course_id,
                    StudyDocument.filename,
                    func.length(StudyDocument.content).label("size"),
                    StudyDocument.created_at,
                    StudyDocument.text_status,
                )
                .join(Course)
                .join(Term)
                .where(Term.account_id == context.id)
            )
            return [
                dict(row) for row in ReadBudget().collect(db.execute(query.limit(10001)).mappings())
            ]

    @router.post("/academic/documents", status_code=201)
    def upload(body: DocumentInput, context=Depends(authenticated)):
        return academic.upload_document(context.id, body.model_dump())

    @router.get("/academic/documents/search")
    def search(
        q: str = Query(min_length=1, max_length=160),
        course_id: str | None = None,
        context=Depends(authenticated),
    ):
        return academic.search_documents(context.id, q, course_id)

    @router.get("/academic/documents/{id}")
    def document(id: str, context=Depends(authenticated)):
        return academic.document(context.id, id)

    @router.get("/academic/documents/{id}/download")
    def download(id: str, context=Depends(authenticated)):
        filename, content = academic.document(context.id, id, download=True)
        return Response(
            content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)},
        )

    @router.delete("/academic/documents/{id}", status_code=204)
    def delete_document(id: str, context=Depends(authenticated)):
        academic.delete_academic(context.id, "documents", id)

    def batch_routes(kind, path):
        def preview(body: dict, context=Depends(authenticated)):
            return batches.preview(context.id, context.token, kind, body)

        def confirm(id: str, context=Depends(authenticated)):
            return batches.confirm(context.id, context.token, kind, id)

        def cancel(id: str, context=Depends(authenticated)):
            batches.cancel(context.id, context.token, kind, id)

        router.add_api_route(path + "/preview", preview, methods=["POST"])
        router.add_api_route(path + "/{id}/confirm", confirm, methods=["POST"])
        router.add_api_route(path + "/{id}", cancel, methods=["DELETE"], status_code=204)

    batch_routes("courses", "/academic/course-batches")
    batch_routes("timetable", "/academic/timetable-batches")

    @router.get("/review/weekly")
    def weekly(end: str | None = None, context=Depends(authenticated)):
        return WeeklyReviewService(engine).review(end, account_id=context.id)

    @router.get("/review/academic")
    def academic_review(context=Depends(authenticated)):
        return academic_snapshot(engine, account_id=context.id)

    @router.get("/planning/preferences")
    def planning_preferences(context=Depends(authenticated)):
        value = prefs.get(context.id, "planning")
        return {**value["values"], "revision": value["revision"]}

    @router.put("/planning/preferences")
    def save_planning(body: dict, context=Depends(authenticated)):
        values = dict(body)
        revision = values.pop("revision", None)
        saved = prefs.put(context.id, "planning", values, revision)
        return {**saved["values"], "revision": saved["revision"]}

    @router.delete("/planning/preferences")
    def reset_planning(body: dict, context=Depends(authenticated)):
        saved = prefs.put(context.id, "planning", {}, body.get("revision"), reset=True)
        return {**saved["values"], "revision": saved["revision"]}

    @router.post("/planning/propose")
    def propose(body: dict, context=Depends(authenticated)):
        result = planning.propose(context.id, context.token, body)
        if result["proposal"] is None:
            return result
        proposal = result["proposal"]
        return {
            "proposal": {"id": proposal["id"], "kind": "event", "payload": proposal["record"]},
            "existing": None,
            "overdue": proposal["overdue"],
            "deadline_ignored": bool(body.get("allow_after_due")),
            "stale_sources": notices.stale_sources(context.id),
        }

    @router.get("/planning/suggestions")
    def planning_suggestion(context=Depends(authenticated)):
        return ProactivePlanning(engine).suggestion(context.id)

    @router.post("/planning/suggestions/dismiss")
    def snooze_suggestion(body: dict, context=Depends(authenticated)):
        id = body.get("id")
        if not isinstance(id, str) or not 1 <= len(id) <= 128:
            raise ValueError("Invalid suggestion")
        return ProactivePlanning(engine).dismiss(context.id, id)

    @router.get("/assistant/preferences")
    def secretary_controls(context=Depends(authenticated)):
        return prefs.get(context.id, "secretary")

    @router.put("/assistant/preferences")
    def save_secretary_controls(body: dict, context=Depends(authenticated)):
        values = dict(body)
        revision = values.pop("revision", None)
        return prefs.put(context.id, "secretary", values, revision)

    @router.delete("/assistant/preferences")
    def reset_secretary_controls(body: dict, context=Depends(authenticated)):
        return prefs.put(context.id, "secretary", {}, body.get("revision"), reset=True)

    @router.post("/planning/suggestions/propose")
    def review_suggestion(body: dict, context=Depends(authenticated)):
        id = body.get("id")
        if not isinstance(id, str) or not 1 <= len(id) <= 128:
            raise ValueError("Invalid suggestion")
        return ProactivePlanning(engine).propose(context.id, context.token, id)

    @router.delete("/planning/proposals/{id}", status_code=204)
    def cancel_plan(id: str, context=Depends(authenticated)):
        from .academic import begin_academic_write

        with Session(engine) as db:
            begin_academic_write(db)
            row = db.get(AssistantProposal, id)
            if (
                not row
                or row.session_hash != context.session_hash
                or row.confirmed_id
                or row.kind != "account_task_plan"
            ):
                raise HTTPException(404, "proposal_expired")
            db.delete(row)
            db.commit()

    def schedule(context):
        value = prefs.get(context.id, "briefings")["values"]
        zone = prefs.get(context.id, "settings")["values"]["timezone"]
        with Session(engine) as db:
            latest = db.scalar(
                select(func.max(AccountBriefing.generated_at)).where(
                    AccountBriefing.account_id == context.id
                )
            )
        return {
            **value,
            "timezone": zone,
            "last_run": None,
            "last_error": None,
            "last_generated_at": latest,
        }

    @router.get("/briefings/schedule")
    def briefing_schedule(context=Depends(authenticated)):
        return schedule(context)

    @router.put("/briefings/schedule")
    def save_briefings(body: dict, context=Depends(authenticated)):
        current = prefs.get(context.id, "briefings")
        prefs.put(context.id, "briefings", body, current["revision"])
        return schedule(context)

    @router.post("/briefings/check")
    def check_briefings(context=Depends(authenticated)):
        return {"generated": briefings.generate_due(context.id), "schedule": schedule(context)}

    @router.get("/recommendations")
    def recommendations(context=Depends(authenticated)):
        return notices.recommendations(context.id)

    @router.post("/recommendations/dismiss")
    def dismiss(body: dict, context=Depends(authenticated)):
        notices.mutate(context.id, dismiss_recommendation=body.get("id"))
        return notices.recommendations(context.id)

    @router.get("/notifications")
    def notifications(context=Depends(authenticated)):
        return notices.feed(context.id)

    @router.put("/notifications/preferences")
    def notification_preferences(body: dict, context=Depends(authenticated)):
        current = prefs.get(context.id, "notifications")
        prefs.put(context.id, "notifications", body, current["revision"])
        return notices.feed(context.id)

    @router.post("/notifications/read")
    def read(body: dict, context=Depends(authenticated)):
        return notices.mutate(context.id, read_ids=body.get("ids"))

    @router.post("/notifications/action")
    def action(body: dict, context=Depends(authenticated)):
        return notices.mutate(context.id, action=body)

    @router.get("/assistant/help")
    def help():
        return catalog()

    @router.get("/assistant/status")
    def status():
        return shared_assistant.status()

    @router.get("/assistant/history")
    def conversation(context=Depends(authenticated)):
        return history.history(context.id)

    @router.put("/assistant/history")
    def history_preference(body: dict, context=Depends(authenticated)):
        current = prefs.get(context.id, "history")
        prefs.put(context.id, "history", body, current["revision"])
        return history.history(context.id)

    @router.delete("/assistant/history")
    def clear_history(context_only: bool = False, context=Depends(authenticated)):
        history.clear(context.id, context_only=context_only)
        return history.history(context.id)

    def assistant(context):
        service = AssistantService(engine, None, None, account_id=context.id)
        service.http.close()
        service.infer = shared_assistant.infer
        return service

    @router.post("/assistant/chat")
    def chat(body: ChatInput, context=Depends(authenticated)):
        if body.request_id:
            requests.context(context.id, body.request_id, body.request_version)
        result = history.chat(context.id, assistant(context), body, context.session_hash)
        if body.request_id and not result.get("history_replayed"):
            try:
                result["request_tracking_updated"] = requests.result(
                    context.id,
                    body.request_id,
                    body.request_version,
                    (result.get("proposal") or {}).get("id"),
                )
            except Exception:
                result["request_tracking_updated"] = False
        return result

    @router.post("/assistant/confirm")
    def confirm(body: Confirmation, context=Depends(authenticated)):
        with Session(engine) as db:
            row = db.get(AssistantProposal, body.id)
            if not row or row.session_hash != context.session_hash:
                raise HTTPException(404, "proposal_expired")
            planned = row.kind == "account_task_plan"
        if planned:
            result = {"kind": "event", **planning.confirm(context.id, context.token, body.id)}
        else:
            result = assistant(context).confirm(body.id, context.session_hash)
        try:
            requests.saved(context.id, body.id)
        except Exception:
            result["request_tracking_warning"] = True
        return result

    @router.post("/recurrence/preview")
    def recurring(body: RecurringInput, context=Depends(authenticated)):
        return RecurringEventService(engine, account_id=context.id).preview(
            body, context.session_hash
        )

    @router.post("/recurrence/confirm")
    def recurring_confirm(body: Confirmation, context=Depends(authenticated)):
        return RecurringEventService(engine, account_id=context.id).confirm(
            body.id, context.session_hash
        )

    @router.delete("/recurrence/proposals/{id}", status_code=204)
    def recurring_cancel(id: str, context=Depends(authenticated)):
        RecurringEventService(engine, account_id=context.id).cancel(id, context.session_hash)

    @router.get("/recurrence/series")
    def series(cursor: str | None = None, context=Depends(authenticated)):
        return SeriesManagementService(engine, account_id=context.id).listing(cursor)

    @router.post("/recurrence/series/{id}/deletion-preview")
    def deletion(id: str, body: DeleteInput, context=Depends(authenticated)):
        return SeriesManagementService(engine, account_id=context.id).preview(
            id, body, context.session_hash
        )

    @router.post("/recurrence/series/{id}/reschedule-preview")
    def reschedule(id: str, body: RescheduleInput, context=Depends(authenticated)):
        return SeriesReschedulingService(engine, account_id=context.id).preview(
            id, body, context.session_hash
        )

    def series_actions(path, cls):
        def confirm(body: Confirmation, context=Depends(authenticated)):
            return cls(engine, account_id=context.id).confirm(body.id, context.session_hash)

        def cancel(id: str, context=Depends(authenticated)):
            cls(engine, account_id=context.id).cancel(id, context.session_hash)

        router.add_api_route(path + "/confirm", confirm, methods=["POST"])
        router.add_api_route(path + "/{id}", cancel, methods=["DELETE"], status_code=204)

    series_actions("/recurrence/deletions", SeriesManagementService)
    series_actions("/recurrence/reschedules", SeriesReschedulingService)
