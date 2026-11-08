import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from .google_calendar import GoogleProblem


class MailReview(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")
    all: bool = False
    undo: bool = False

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.id) == self.all or (self.undo and self.all):
            raise ValueError("Choose one message or all")
        return self


def gmail_router(service, authenticated):
    router = APIRouter(prefix="/integrations/gmail", dependencies=[Depends(authenticated)])

    def call(method, *args):
        try:
            return method(*args)
        except GoogleProblem as error:
            raise HTTPException(error.status, error.code) from None
        except Exception:
            raise HTTPException(502, "provider_unavailable") from None

    @router.get("/status")
    def status():
        return call(service.status)

    @router.post("/authorize")
    def authorize(session=Depends(authenticated)):
        origin = f"http://127.0.0.1:{os.environ.get('LIFEOS_WEB_PORT', '3000')}"
        return {"authorization_url": call(service.authorize, session.token_hash, origin)}

    @router.post("/sync")
    def sync(tasks: BackgroundTasks, response: Response, background: bool = False):
        if background:
            state = call(service.status)
            if not state["connected"]:
                raise HTTPException(409, "not_connected")
            if state["syncing"]:
                raise HTTPException(409, "sync_in_progress")

            def run():
                try:
                    service.sync()
                except GoogleProblem:
                    pass  # Error/cache/retry state is persisted by the service.

            tasks.add_task(run)
            response.status_code = 202
            return {"queued": True}
        return call(service.sync)

    @router.post("/disconnect")
    def disconnect():
        call(service.disconnect)
        return call(service.status)

    @router.get("/messages")
    def messages():
        return call(service.messages)

    @router.get("/queue")
    def queue():
        return call(service.queue)

    @router.post("/review")
    def review(body: MailReview):
        return call(service.review, body.id, body.all, body.undo)

    return router
