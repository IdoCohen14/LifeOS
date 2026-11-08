from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .assistant import ChatInput
from .assistant_help import catalog


class Confirmation(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f-]{36}$")


def assistant_router(service, authenticated, history_service):
    router = APIRouter(prefix="/assistant", dependencies=[Depends(authenticated)])

    @router.get("/help")
    def help():
        return catalog()

    @router.get("/status")
    def status():
        return service.status()

    @router.post("/chat")
    def chat(body: ChatInput, session=Depends(authenticated)):
        return history_service.chat(service, body, session.token_hash)

    @router.post("/confirm")
    def confirm(body: Confirmation, session=Depends(authenticated)):
        return service.confirm(body.id, session.token_hash)

    return router
