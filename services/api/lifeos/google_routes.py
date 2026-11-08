import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .google_calendar import GoogleProblem


class GoogleConfig(BaseModel):
    client_id: str = Field(
        pattern=r"^[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com$", max_length=250
    )
    client_secret: str = Field(min_length=1, max_length=512)


class CalendarSelection(BaseModel):
    ids: list[str] = Field(max_length=100)


def google_router(service, authenticated, gmail=None):
    router = APIRouter(prefix="/integrations/google")

    def call(method, *args):
        try:
            return method(*args)
        except GoogleProblem as error:
            raise HTTPException(error.status, error.code) from None
        except Exception:
            raise HTTPException(502, "provider_unavailable") from None

    @router.get("/status", dependencies=[Depends(authenticated)])
    def status():
        return call(service.status)

    @router.post("/config", dependencies=[Depends(authenticated)])
    def configure(body: GoogleConfig):
        if os.environ.get("LIFEOS_TEST_MODE") != "1":
            raise HTTPException(404, "not_found")
        call(service.configure, body.client_id, body.client_secret)
        return service.status()

    @router.post("/authorize")
    def authorize(session=Depends(authenticated)):
        origin = f"http://127.0.0.1:{os.environ.get('LIFEOS_WEB_PORT', '3000')}"
        url = call(service.authorize, session.token_hash, origin)
        return {"authorization_url": url}

    @router.get("/callback")
    def callback(
        state: str = Query(max_length=128),
        code: str | None = Query(default=None, max_length=4096),
        error: str | None = Query(default=None, max_length=200),
    ):
        try:
            target = gmail if gmail and state.startswith("gmail.") else service
            target.callback(state, code, error)
        except GoogleProblem as problem:
            if problem.code == "invalid_oauth_state":
                raise HTTPException(400, problem.code) from None
            return RedirectResponse("/?view=settings&google=error", status_code=303)
        except Exception:
            return RedirectResponse("/?view=settings&google=error", status_code=303)
        return RedirectResponse("/?view=settings&google=connected", status_code=303)

    @router.post("/sync", dependencies=[Depends(authenticated)])
    def sync():
        return call(service.sync)

    @router.put("/calendars", dependencies=[Depends(authenticated)])
    def select(body: CalendarSelection):
        call(service.select, body.ids)
        return service.status()

    @router.post("/disconnect", dependencies=[Depends(authenticated)])
    def disconnect():
        call(service.disconnect)
        return service.status()

    @router.get("/events", dependencies=[Depends(authenticated)])
    def events():
        return call(service.events)

    return router
