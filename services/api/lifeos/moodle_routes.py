from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from .google_calendar import GoogleProblem


def moodle_router(service, authenticated):
    router = APIRouter(prefix="/integrations/moodle", dependencies=[Depends(authenticated)])

    def call(method, *args):
        try:
            return method(*args)
        except GoogleProblem as error:
            raise HTTPException(error.status, error.code) from None
        except Exception:
            raise HTTPException(502, "feed_unavailable") from None

    @router.get("/status")
    def status():
        return call(service.status)

    @router.get("/events")
    def events():
        return call(service.events)

    @router.get("/changes")
    def changes():
        return call(service.changes)

    @router.post("/config")
    async def configure(request: Request):
        try:
            body = await request.json()
            url = body["url"].strip()
        except Exception:
            raise HTTPException(422, "invalid_moodle_url") from None
        return call(service.configure_feed, url)

    @router.post("/sync")
    def sync(tasks: BackgroundTasks, response: Response, background: bool = False):
        state = call(service.status)
        if not state["configured"]:
            raise HTTPException(409, "not_configured")
        if state["syncing"]:
            raise HTTPException(409, "sync_in_progress")
        if background:

            def run():
                try:
                    service.sync()
                except GoogleProblem:
                    pass

            tasks.add_task(run)
            response.status_code = 202
            return {"queued": True}
        return call(service.sync)

    @router.post("/disconnect")
    def disconnect():
        call(service.disconnect)
        return call(service.status)

    return router
