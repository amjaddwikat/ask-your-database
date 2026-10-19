"""Conversation memory: the last few turns of each session, fed back into agent prompts."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncEngine

metadata = MetaData()

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), nullable=False, index=True),
    Column("role", String(16), nullable=False),  # "user" | "assistant"
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    created_at: datetime


class ConversationStore:
    def __init__(self, engine: AsyncEngine, window: int) -> None:
        self._engine = engine
        self._window = window

    async def create_tables(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def recent(self, session_id: str, limit: int | None = None) -> list[Message]:
        """Most recent messages for a session, oldest first."""
        stmt = (
            select(messages.c.role, messages.c.content, messages.c.created_at)
            .where(messages.c.session_id == session_id)
            .order_by(messages.c.id.desc())
            .limit(limit or self._window)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return [Message(r.role, r.content, r.created_at) for r in reversed(rows)]

    async def append(self, session_id: str, role: str, content: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(messages).values(
                    session_id=session_id,
                    role=role,
                    content=content,
                    created_at=datetime.now(UTC),
                )
            )


def format_history(history: list[Message], max_chars: int = 1500) -> str:
    """Render history for a prompt, truncating long messages to keep token usage bounded."""
    if not history:
        return "(no previous messages)"
    lines = []
    for m in history:
        content = m.content if len(m.content) <= max_chars else m.content[:max_chars] + "..."
        lines.append(f"{m.role.upper()}: {content}")
    return "\n".join(lines)
