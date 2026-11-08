"""Account recovery uses process-key/origin controls; owner changes also require CSRF/session."""

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .account_lifecycle import AccountLifecycleService


class PasswordProof(BaseModel):
    password: str = Field(min_length=8, max_length=1024)


class RecoveryInput(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    recovery_key: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=1024)


class DeletionInput(PasswordProof):
    preview_id: str = Field(min_length=36, max_length=36)
    login: str = Field(min_length=1, max_length=254)


def bind_lifecycle(router, auth, directory, authenticated):
    lifecycle = AccountLifecycleService(auth, directory)

    @router.get("/access")
    def status(context=Depends(authenticated)):
        return lifecycle.status(context.id, context.token)

    @router.post("/access/key")
    def generate(body: PasswordProof, context=Depends(authenticated)):
        return lifecycle.generate_key(context.id, context.token, body.password)

    @router.post("/deletion/preview")
    def preview(context=Depends(authenticated)):
        return lifecycle.deletion_preview(context.id, context.token)

    @router.post("/deletion/confirm")
    def confirm(body: DeletionInput, response: Response, context=Depends(authenticated)):
        result = lifecycle.confirm_deletion(
            context.id, context.token, body.preview_id, body.password, body.login
        )
        response.delete_cookie("lifeos_session", path="/")
        if not result["deleted"]:
            response.status_code = 202
        return result

    @router.post("/access/recover", status_code=204)
    def recover(body: RecoveryInput, response: Response):
        try:
            success = lifecycle.recover(body.login, body.recovery_key, body.new_password)
        except RuntimeError:
            raise HTTPException(
                429, "Recovery busy; retry later", headers={"Retry-After": "60"}
            ) from None
        if not success:
            raise HTTPException(401, "Recovery details are invalid or unavailable")
        response.delete_cookie("lifeos_session", path="/")
