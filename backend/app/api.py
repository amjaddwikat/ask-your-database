import hmac
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.db.memory import ConversationStore
from app.db.warehouse import Warehouse
from app.orchestrator import Orchestrator
from app.schemas import ChatRequest, ChatResponse, ErrorResponse, HistoryMessage, TableInfo


def require_api_key(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.settings.api_key.get_secret_value()
    # compare_digest avoids leaking the key through response-time differences.
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key")


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator  # type: ignore[no-any-return]


def get_memory(request: Request) -> ConversationStore:
    return request.app.state.memory  # type: ignore[no-any-return]


def get_warehouse(request: Request) -> Warehouse:
    return request.app.state.warehouse  # type: ignore[no-any-return]


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)


@router.post("/chat", response_model=ChatResponse, summary="Ask a question in plain language")
async def chat(
    body: ChatRequest, orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)]
) -> ChatResponse:
    session_id = body.session_id or uuid.uuid4().hex
    return await orchestrator.handle(session_id, body.message.strip())


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[HistoryMessage],
    summary="Conversation history for a session",
)
async def session_messages(
    session_id: str, memory: Annotated[ConversationStore, Depends(get_memory)]
) -> list[HistoryMessage]:
    history = await memory.recent(session_id, limit=100)
    return [
        HistoryMessage(role=m.role, content=m.content, created_at=m.created_at.isoformat())
        for m in history
    ]


@router.get("/schema", response_model=list[TableInfo], summary="Tables the assistant can query")
async def schema(warehouse: Annotated[Warehouse, Depends(get_warehouse)]) -> list[TableInfo]:
    assert warehouse.schema is not None
    return [
        TableInfo(name=t.qualified_name, columns={c.name: c.data_type for c in t.columns})
        for t in warehouse.schema.tables
    ]
