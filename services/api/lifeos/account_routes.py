"""Explicit local account mode. Legacy workspace routes never receive owned sessions."""

import hmac
import os
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .account_academic import AccountAcademic
from .account_preferences import AccountPreferences
from .account_records import AccountRecords
from .accounts import AccountService
from .assistant import session_scope
from .deployment import DeploymentConfig
from .google_calendar import GoogleProblem
from .models import Account, LoginSession
from .security import token_hash


class AccountRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request):
            try:
                return await handler(request)
            except HTTPException:
                raise
            except GoogleProblem as error:
                raise HTTPException(error.status, error.code) from None
            except PermissionError:
                raise HTTPException(403, "account_access_denied") from None
            except LookupError:
                raise HTTPException(404, "record_not_found") from None
            except ValidationError:
                raise HTTPException(422, "invalid_request") from None
            except ValueError:
                raise HTTPException(409, "workspace_changed_or_invalid_input") from None
            except RuntimeError:
                raise HTTPException(409, "workspace_busy") from None

        return bounded


class Credentials(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=8, max_length=1024)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


@dataclass(frozen=True)
class AccountContext:
    id: str
    token: str
    session_hash: str
    csrf: str
    login: str


def account_router(engine, directory, *, enabled, shared_assistant):
    deployment = DeploymentConfig.from_env()
    auth = AccountService(engine, enabled=enabled)

    def mode():
        if not enabled:
            raise HTTPException(404, "not_found")

    router = APIRouter(prefix="/accounts", route_class=AccountRoute, dependencies=[Depends(mode)])

    def authenticated(request: Request):
        token = request.cookies.get("lifeos_session", "")
        with Session(engine) as db:
            session = db.get(LoginSession, token_hash(token))
            if not session or session.account_id is None or session.expires <= time.time():
                raise HTTPException(401, "session_expired")
            if not deployment.allows_account(session.account_id):
                raise HTTPException(401, "session_expired")
            session_scope(db, session.token_hash, session.account_id)
            if request.method not in ("GET", "HEAD") and not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session.csrf
            ):
                raise HTTPException(403, "invalid_csrf_token")
            return AccountContext(
                session.account_id,
                token,
                session.token_hash,
                session.csrf,
                db.get(Account, session.account_id).login,
            )

    @router.post("/register", status_code=201)
    def register(body: Credentials):
        auth.register(body.login, body.password)
        return {"created": True}

    @router.post("/session")
    def login(body: Credentials, response: Response):
        result = auth.login(body.login, body.password)
        if result is None:
            raise HTTPException(401, "invalid_credentials")
        response.set_cookie(
            "lifeos_session",
            result["token"],
            httponly=True,
            secure=deployment.secure_cookies,
            samesite="lax",
            max_age=43200,
            path="/",
        )
        with Session(engine) as db:
            login_name = db.get(Account, result["account_id"]).login
        return {
            "csrf": result["csrf"],
            "account_id": result["account_id"],
            "login": login_name,
            "account_mode": True,
        }

    @router.get("/session")
    def session(context=Depends(authenticated)):
        return {
            "csrf": context.csrf,
            "account_id": context.id,
            "login": context.login,
            "account_mode": True,
            "test_mode": os.environ.get("LIFEOS_TEST_MODE") == "1",
        }

    @router.delete("/session", status_code=204)
    def logout(response: Response, context=Depends(authenticated)):
        auth.logout(context.token)
        response.delete_cookie("lifeos_session", path="/")

    @router.put("/password", status_code=204)
    def password(body: PasswordChange, response: Response, context=Depends(authenticated)):
        if not auth.change_password(context.id, body.current_password, body.new_password):
            raise HTTPException(401, "invalid_credentials")
        response.delete_cookie("lifeos_session", path="/")

    workspace = APIRouter(
        prefix="/workspace", route_class=AccountRoute, dependencies=[Depends(authenticated)]
    )
    records, academic, prefs = (
        AccountRecords(engine),
        AccountAcademic(engine),
        AccountPreferences(engine),
    )

    @workspace.get("/settings")
    def settings(context=Depends(authenticated)):
        return {"id": 1, **prefs.get(context.id, "settings")["values"]}

    @workspace.put("/settings")
    def save_settings(body: dict, context=Depends(authenticated)):
        current = prefs.get(context.id, "settings")
        return {"id": 1, **prefs.put(context.id, "settings", body, current["revision"])["values"]}

    # Fixed route factories keep model kinds out of user-controlled ownership decisions.
    def manual(kind):
        def listing(context=Depends(authenticated)):
            return records.list(context.id, kind)

        def create(body: dict, context=Depends(authenticated)):
            return records.save(context.id, kind, body)

        def update(id: str, body: dict, context=Depends(authenticated)):
            return records.save(context.id, kind, body, id)

        def remove(id: str, context=Depends(authenticated)):
            records.delete(context.id, kind, id)

        workspace.add_api_route("/" + kind, listing, methods=["GET"])
        workspace.add_api_route("/" + kind, create, methods=["POST"], status_code=201)
        workspace.add_api_route("/" + kind + "/{id}", update, methods=["PUT"])
        workspace.add_api_route("/" + kind + "/{id}", remove, methods=["DELETE"], status_code=204)

    for kind in ("tasks", "events"):
        manual(kind)

    def academic_kind(kind):
        root = kind in ("terms", "courses")

        def listing(context=Depends(authenticated)):
            return (
                academic.list_roots(context.id, kind)
                if root
                else academic.list_children(context.id, kind)
            )

        def create(body: dict, context=Depends(authenticated)):
            return (
                academic.save_root(context.id, kind, body)
                if root
                else academic.save_child(context.id, kind, body)
            )

        def update(id: str, body: dict, context=Depends(authenticated)):
            return (
                academic.save_root(context.id, kind, body, id)
                if root
                else academic.save_child(context.id, kind, body, id)
            )

        def remove(id: str, context=Depends(authenticated)):
            academic.delete_academic(context.id, kind, id)

        path = "/academic/" + kind
        workspace.add_api_route(path, listing, methods=["GET"])
        workspace.add_api_route(path, create, methods=["POST"], status_code=201)
        workspace.add_api_route(path + "/{id}", update, methods=["PUT"])
        workspace.add_api_route(path + "/{id}", remove, methods=["DELETE"], status_code=204)

    for kind in ("terms", "courses", "items", "grades", "timetable"):
        academic_kind(kind)

    from .account_workspace_routes import bind_workspace

    bind_workspace(workspace, engine, directory, authenticated, shared_assistant)
    from .account_provider_routes import bind_providers

    bind_providers(router, workspace, engine, directory, authenticated)
    from .account_lifecycle_routes import bind_lifecycle

    bind_lifecycle(router, auth, directory, authenticated)
    router.include_router(workspace)
    return router
