"""Test doubles: a scripted LLM and an in-memory warehouse that still uses the real QueryGuard."""

import json
from collections import deque
from typing import Any, ClassVar

from app.db.guard import QueryGuard
from app.db.warehouse import (
    Column,
    QueryExecutionError,
    QueryResult,
    Table,
    Warehouse,
    WarehouseSchema,
)

SCHEMA = WarehouseSchema(
    tables=(
        Table(
            "telecom_dw",
            "dimcustomer",
            (Column("CustomerID", "int"), Column("Age", "int"), Column("ContractType", "varchar")),
        ),
        Table(
            "telecom_dw",
            "factbilling",
            (Column("BillingID", "int"), Column("CustomerID", "int"), Column("BillAmount", "dec")),
        ),
    )
)


class FakeLLM:
    """Returns queued replies per agent, identified by a phrase in its system prompt."""

    AGENTS: ClassVar[dict[str, str]] = {
        "router": "Router Agent",
        "sql": "SQL Agent",
        "analysis": "Analysis Agent",
        "plot": "Plot Agent",
    }

    def __init__(self) -> None:
        self.replies: dict[str, deque[str]] = {name: deque() for name in self.AGENTS}
        self.calls: list[tuple[str, str]] = []  # (agent, user prompt)
        self.system_prompts: list[tuple[str, str]] = []  # (agent, system prompt)

    def reply(self, agent: str, *replies: str | dict[str, Any]) -> "FakeLLM":
        for r in replies:
            self.replies[agent].append(r if isinstance(r, str) else json.dumps(r))
        return self

    async def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        agent = next(name for name, marker in self.AGENTS.items() if marker in system)
        self.calls.append((agent, user))
        self.system_prompts.append((agent, system))
        if not self.replies[agent]:
            raise AssertionError(f"No scripted reply left for the {agent} agent")
        return self.replies[agent].popleft()

    def calls_to(self, agent: str) -> list[str]:
        return [user for name, user in self.calls if name == agent]


class FakeWarehouse(Warehouse):
    """Validates SQL with the real guard, then returns canned rows instead of hitting MySQL."""

    def __init__(self, rows: list[dict[str, Any]] | None = None, max_rows: int = 500) -> None:
        self.schema = SCHEMA
        self._guard = QueryGuard(SCHEMA.table_names, "telecom_dw", max_rows)
        self._max_rows = max_rows
        self.rows = rows if rows is not None else []
        self.fail_with: str | None = None
        self.executed: list[str] = []

    async def run(self, sql: str) -> QueryResult:
        safe = self.guard.validate(sql)
        self.executed.append(safe)
        if self.fail_with:
            message, self.fail_with = self.fail_with, None
            raise QueryExecutionError(message)
        columns = list(self.rows[0]) if self.rows else []
        return QueryResult(safe, columns, list(self.rows), elapsed_ms=1.0)

    async def ping(self) -> None:
        return None
