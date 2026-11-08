"""Owned provider consent, local mail review, devices and archive HTTP adapters."""

import os

from fastapi import BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import Field

from .account_archive import AccountArchive
from .account_backup_schedule import AccountBackupSchedule
from .account_braude import AccountBraude, validate_portal_url
from .account_calendar import AccountCalendar
from .account_gmail import AccountGmail
from .account_mail import AccountMail
from .account_moodle import AccountMoodle
from .account_moodle_changes import AccountMoodleChanges
from .account_oauth import AccountOAuth
from .account_preferences import AccountPreferences
from .account_providers import AccountProviders
from .account_restore import AccountRestore
from .backup_inspection import InspectionInput
from .deployment import DeploymentConfig
from .gmail_routes import MailReview
from .google_routes import CalendarSelection, GoogleConfig
from .moodle import validate_url
from .web_push import ConfigInput, Lookup, WebPushService
from .web_push_transport import SubscriptionInput


class OwnedMailReview(MailReview):
    revision: int = Field(ge=0)


def bind_providers(router, workspace, engine, directory, authenticated):
    deployment = DeploymentConfig.from_env()
    store, oauth = AccountProviders(engine, directory), AccountOAuth(engine, directory)
    calendar, gmail, moodle = (
        AccountCalendar(engine, directory),
        AccountGmail(engine, directory),
        AccountMoodle(engine, directory),
    )
    mail, archives = AccountMail(engine), AccountArchive(engine, directory)
    backups, restore = AccountBackupSchedule(engine, directory), AccountRestore(engine, directory)
    adapters = {"google": calendar, "gmail": gmail, "moodle": moodle, "braude": AccountBraude(engine, directory)}

    def status(account_id, provider):
        store.validate_provider(provider)
        result = store.status(account_id, provider)
        app_configured = provider not in {"moodle", "braude"} and bool(
            os.environ.get("LIFEOS_GOOGLE_CLIENT_ID")
            and os.environ.get("LIFEOS_GOOGLE_CLIENT_SECRET")
        )
        result["configured"] = result["configured"] or app_configured
        result["connected"] = (
            result["authorized"] if provider not in {"moodle", "braude"} else result["last_success"] is not None
        )
        result["state"] = (
            "syncing"
            if result["syncing"]
            else "error"
            if result["error"]
            else "connected"
            if result["connected"]
            else "configured"
            if result["configured"]
            else "disconnected"
        )
        if provider == "google":
            result.update(
                calendars=calendar.calendars(account_id), window_days={"past": 30, "future": 365}
            )
        elif provider == "gmail":
            result.update(limit=50, revision=mail.get(account_id)["revision"])
            result["automatic_calendar"] = AccountPreferences(engine).get(account_id, "mail_calendar")["values"]["enabled"]
        else:
            result["event_count"] = len(store.records(account_id, provider))
        return result

    @workspace.get("/integrations/{provider}/status")
    def provider_status(provider: str, context=Depends(authenticated)):
        return status(context.id, provider)

    @workspace.post("/integrations/{provider}/authorize")
    def authorize(provider: str, response: Response, context=Depends(authenticated)):
        oauth.prepare_application(context.id, provider)
        url = oauth.start(
            context.id,
            provider,
            context.token,
            web_port=int(os.environ.get("LIFEOS_WEB_PORT", "3000")),
        )
        # Upgrade a transferred Strict cookie only on explicit authorization.
        response.set_cookie(
            "lifeos_session", context.token, httponly=True, secure=deployment.secure_cookies, samesite="lax", max_age=43200, path="/"
        )
        return {"authorization_url": url}

    @router.get("/oauth/callback")
    def callback(
        state: str = Query(max_length=128),
        code: str | None = Query(default=None, max_length=4096),
        error: str | None = Query(default=None, max_length=200),
        context=Depends(authenticated),
    ):
        if error or code is None:
            return RedirectResponse("/?view=settings&google=error", status_code=303)
        try:
            oauth.finish(context.id, context.token, state, code)
        except (ValueError, PermissionError):
            raise HTTPException(400, "invalid_oauth_state") from None
        return RedirectResponse("/?view=settings&google=connected", status_code=303)

    @workspace.post("/integrations/google/config")
    def google_config(body: GoogleConfig, context=Depends(authenticated)):
        if os.environ.get("LIFEOS_TEST_MODE") != "1":
            raise HTTPException(404, "not_found")
        store.configure(context.id, "google", body.model_dump())
        return status(context.id, "google")

    @workspace.post("/integrations/gmail/calendar")
    def mail_calendar_config(body: dict, context=Depends(authenticated)):
        if type(body.get("enabled")) is not bool:
            raise HTTPException(422, "invalid_calendar_preference")
        prefs = AccountPreferences(engine)
        current = prefs.get(context.id, "mail_calendar")
        prefs.put(context.id, "mail_calendar", {"enabled": body["enabled"]}, current["revision"])
        return status(context.id, "gmail")

    @workspace.post("/integrations/moodle/config")
    def moodle_config(body: dict, context=Depends(authenticated)):
        value = body.get("url")
        if not isinstance(value, str):
            raise HTTPException(422, "invalid_moodle_url")
        store.configure(context.id, "moodle", {"url": validate_url(value.strip())})
        return status(context.id, "moodle")

    @workspace.post("/integrations/braude/config")
    def braude_config(body: dict, context=Depends(authenticated)):
        value = body.get("url")
        if not isinstance(value, str):
            raise HTTPException(422, "invalid_portal_url")
        validated = validate_portal_url(value.strip())
        store.configure(context.id, "braude", {"url": validated})
        return status(context.id, "braude")

    @workspace.post("/integrations/{provider}/sync")
    def sync(
        provider: str,
        tasks: BackgroundTasks,
        response: Response,
        background: bool = False,
        context=Depends(authenticated),
    ):
        store.validate_provider(provider)
        if not store.status(context.id, provider)["authorized"]:
            raise HTTPException(409, "not_configured")
        if background:

            def run():
                try:
                    adapters[provider].sync(context.id)
                except Exception:
                    pass  # The adapter persists sanitized owned failure/backoff state.

            tasks.add_task(run)
            response.status_code = 202
            return {"queued": True}
        adapters[provider].sync(context.id)
        return status(context.id, provider)

    @workspace.post("/integrations/{provider}/disconnect")
    def disconnect(provider: str, context=Depends(authenticated)):
        store.configure(context.id, provider, {})
        return status(context.id, provider)

    @workspace.get("/integrations/{provider}/events")
    def events(provider: str, context=Depends(authenticated)):
        if provider == "google":
            return calendar.events(context.id)
        if provider in {"moodle", "braude"}:
            return store.records(context.id, provider, calendar_only=True)
        raise HTTPException(404, "not_found")

    @workspace.put("/integrations/google/calendars")
    def select_calendars(body: CalendarSelection, context=Depends(authenticated)):
        calendar.select(context.id, body.ids)
        return status(context.id, "google")

    @workspace.get("/integrations/moodle/changes")
    def changes(context=Depends(authenticated)):
        return AccountMoodleChanges(engine).list(context.id)

    def messages(account_id, *, queue=False):
        snapshot = mail.get(account_id)
        return [
            {**row, "connection_revision": snapshot["revision"]}
            for row in snapshot["queue" if queue else "messages"]
        ]

    @workspace.get("/integrations/gmail/messages")
    def mail_messages(context=Depends(authenticated)):
        return messages(context.id)

    @workspace.get("/integrations/gmail/queue")
    def mail_queue(context=Depends(authenticated)):
        return messages(context.id, queue=True)

    @workspace.post("/integrations/gmail/review")
    def review(body: OwnedMailReview, context=Depends(authenticated)):
        snapshot = mail.review(
            context.id, body.revision, message_id=body.id, all=body.all, undo=body.undo
        )
        return [{**row, "connection_revision": snapshot["revision"]} for row in snapshot["queue"]]

    def push(context):
        return WebPushService(engine, directory, account_id=context.id)

    @workspace.get("/push/config")
    def push_config(context=Depends(authenticated)):
        return push(context).config()

    @workspace.put("/push/config")
    def configure_push(body: ConfigInput, context=Depends(authenticated)):
        return push(context).configure(body)

    @workspace.get("/push/subscriptions")
    def devices(context=Depends(authenticated)):
        return push(context).devices()

    @workspace.post("/push/subscriptions")
    def register_device(body: SubscriptionInput, context=Depends(authenticated)):
        return push(context).register(body)

    @workspace.post("/push/lookup")
    def lookup(body: Lookup, context=Depends(authenticated)):
        return push(context).lookup(body.endpoint)

    @workspace.get("/push/subscriptions/{id}")
    def device(id: str, context=Depends(authenticated)):
        return push(context).status(id)

    @workspace.delete("/push/subscriptions/{id}", status_code=204)
    def remove_device(id: str, context=Depends(authenticated)):
        push(context).remove(id)

    @workspace.get("/recovery/export")
    def export(context=Depends(authenticated)):
        return Response(
            archives.export_public(context.id),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="LifeOS-account-export.json"'},
        )

    @workspace.get("/recovery/backups")
    def archive_list(context=Depends(authenticated)):
        return archives.list(context.id)

    @workspace.post("/recovery/backups", status_code=201)
    def create_archive(body: InspectionInput, context=Depends(authenticated)):
        return archives.create(context.id, body.password.get_secret_value())

    @workspace.get("/recovery/backups/{id}")
    def download_archive(id: str, context=Depends(authenticated)):
        path = archives.file(context.id, id)
        if not path.is_file():
            raise HTTPException(404, "backup_not_found")
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename="LifeOS-" + id + ".lifeosaccountbackup",
        )

    @workspace.post("/recovery/backups/{id}/inspect")
    def inspect_archive(id: str, body: InspectionInput, context=Depends(authenticated)):
        return {
            "valid": True,
            "schema": "account-1",
            **archives.inspect(context.id, id, body.password.get_secret_value()),
        }

    @workspace.post("/recovery/backups/{id}/restore-preview")
    def restore_preview(id: str, body: InspectionInput, context=Depends(authenticated)):
        return restore.preview(context.id, context.token, id, body.password.get_secret_value())

    @workspace.post("/recovery/restore/{id}/confirm")
    def restore_confirm(
        id: str, body: InspectionInput, response: Response, context=Depends(authenticated)
    ):
        result = restore.confirm(context.id, context.token, id, body.password.get_secret_value())
        response.delete_cookie("lifeos_session", path="/")
        return result

    @workspace.get("/recovery/schedule")
    def backup_schedule(context=Depends(authenticated)):
        return backups.get(context.id)

    @workspace.put("/recovery/schedule")
    def save_backup_schedule(body: dict, context=Depends(authenticated)):
        return backups.configure(context.id, body)
