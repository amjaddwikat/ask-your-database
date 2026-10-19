"""Request/response models for the public HTTP API."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.plot import ChartSpec

ResponseType = Literal["general", "blocked", "clarification", "analysis", "plot", "error"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{8,64}$",
        description="Omit to start a new conversation; reuse the returned id to continue it.",
    )


class StepTrace(BaseModel):
    step: str
    duration_ms: float
    detail: str | None = None


class QueryData(BaseModel):
    sql: str
    explanation: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


class Chart(BaseModel):
    spec: ChartSpec
    data: list[dict[str, Any]]


class ChatResponse(BaseModel):
    session_id: str
    type: ResponseType
    message: str = Field(description="Markdown text to show the user")
    query: QueryData | None = None
    chart: Chart | None = None
    trace: list[StepTrace] = Field(
        default_factory=list, description="Which agents ran and how long each took"
    )


class HistoryMessage(BaseModel):
    role: str
    content: str
    created_at: str


class TableInfo(BaseModel):
    name: str
    columns: dict[str, str]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
