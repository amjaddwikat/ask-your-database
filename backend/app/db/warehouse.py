"""Read-only access to the data warehouse the agents query."""

import datetime as dt
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, bindparam, event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.db.guard import QueryGuard

logger = logging.getLogger(__name__)


class QueryExecutionError(RuntimeError):
    """The database rejected or failed a query. The message is safe to show to users."""


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    columns: tuple[Column, ...]

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class ForeignKey:
    source: str  # schema.table.column
    target: str


@dataclass(frozen=True)
class DateCoverage:
    column: str  # schema.table.column
    earliest: dt.date
    latest: dt.date


DATE_TYPES = ("date", "datetime", "timestamp")


@dataclass(frozen=True)
class WarehouseSchema:
    tables: tuple[Table, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()
    date_coverage: tuple[DateCoverage, ...] = ()

    @property
    def table_names(self) -> set[str]:
        return {t.qualified_name for t in self.tables}

    @property
    def latest_date(self) -> dt.date | None:
        """The most recent date anywhere in the data: the warehouse's notion of "today"."""
        return max((c.latest for c in self.date_coverage), default=None)

    def time_context(self) -> str:
        """How agents should read relative periods ("last 6 months") against historical data."""
        latest = self.latest_date
        if latest is None:
            return "No date range is known for this data."
        day = latest.isoformat()
        return (
            f"The data is a historical snapshot whose most recent date is {day}. "
            f'Treat {day} as "today": relative periods such as "last 6 months", "this year" or '
            f'"recently" end on that date. Dates up to {day} are not in the future.'
        )

    def describe(self) -> str:
        """Compact text form of the schema, used inside LLM prompts."""
        lines: list[str] = []
        for t in self.tables:
            cols = ", ".join(f"{c.name} {c.data_type}" for c in t.columns)
            lines.append(f"- {t.qualified_name}({cols})")
        if self.foreign_keys:
            lines.append("\nRelationships:")
            lines.extend(f"- {fk.source} -> {fk.target}" for fk in self.foreign_keys)
        if self.date_coverage:
            lines.append("\nDate coverage:")
            lines.extend(
                f"- {c.column}: {c.earliest.isoformat()} to {c.latest.isoformat()}"
                for c in self.date_coverage
            )
            lines.append(self.time_context())
        return "\n".join(lines)


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    elapsed_ms: float
    truncated: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.date | dt.datetime | dt.time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def create_warehouse_engine(url: str, query_timeout_ms: int) -> AsyncEngine:
    engine = create_async_engine(
        url, pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _harden_session(dbapi_conn: Any, _record: Any) -> None:
        # Defence in depth on top of the read-only DB user and the QueryGuard:
        # every pooled connection is read-only and has a server-side SELECT timeout.
        cursor = dbapi_conn.cursor()
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(query_timeout_ms)}")
        cursor.close()

    return engine


class Warehouse:
    def __init__(self, engine: AsyncEngine, max_rows: int) -> None:
        self._engine = engine
        self._max_rows = max_rows
        self._guard: QueryGuard | None = None
        self.schema: WarehouseSchema | None = None

    async def load_schema(self, schemas: list[str]) -> WarehouseSchema:
        """Introspect tables, columns and foreign keys so prompts never drift from the DB."""
        params = {"schemas": schemas}
        async with self._engine.connect() as conn:
            col_rows = (
                await conn.execute(
                    text(
                        "SELECT table_schema, table_name, column_name, column_type "
                        "FROM information_schema.columns WHERE table_schema IN :schemas "
                        "ORDER BY table_schema, table_name, ordinal_position"
                    ).bindparams(bindparam("schemas", expanding=True)),
                    params,
                )
            ).all()
            fk_rows = (
                await conn.execute(
                    text(
                        "SELECT table_schema, table_name, column_name, referenced_table_schema, "
                        "referenced_table_name, referenced_column_name "
                        "FROM information_schema.key_column_usage "
                        "WHERE table_schema IN :schemas AND referenced_table_name IS NOT NULL"
                    ).bindparams(bindparam("schemas", expanding=True)),
                    params,
                )
            ).all()
            coverage = await _load_date_coverage(conn, col_rows)

        tables: dict[tuple[str, str], list[Column]] = {}
        for schema, table, column, col_type in col_rows:
            tables.setdefault((schema, table), []).append(Column(column, col_type))
        self.schema = WarehouseSchema(
            tables=tuple(Table(s, t, tuple(cols)) for (s, t), cols in tables.items()),
            foreign_keys=tuple(
                ForeignKey(f"{s}.{t}.{c}", f"{rs}.{rt}.{rc}") for s, t, c, rs, rt, rc in fk_rows
            ),
            date_coverage=coverage,
        )
        self._guard = QueryGuard(
            self.schema.table_names, default_schema=schemas[0], max_rows=self._max_rows
        )
        logger.info("Loaded warehouse schema: %d tables", len(self.schema.tables))
        return self.schema

    @property
    def guard(self) -> QueryGuard:
        if self._guard is None:
            raise RuntimeError("load_schema() must be called before running queries")
        return self._guard

    async def run(self, sql: str) -> QueryResult:
        safe_sql = self.guard.validate(sql)  # raises UnsafeQueryError
        started = time.perf_counter()
        try:
            async with self._engine.connect() as conn:
                # no_parameters: send the SQL as-is, so '%' in LIKE patterns isn't
                # treated as a driver placeholder.
                raw_conn = await conn.execution_options(no_parameters=True)
                result = await raw_conn.exec_driver_sql(safe_sql)
                columns = list(result.keys())
                rows = [{k: _to_json_safe(v) for k, v in row._mapping.items()} for row in result]
        except Exception as e:
            logger.warning("Warehouse query failed: %s | sql=%s", e, safe_sql)
            raise QueryExecutionError(_describe_db_error(e)) from e
        elapsed = (time.perf_counter() - started) * 1000
        return QueryResult(
            safe_sql,
            columns,
            rows,
            elapsed_ms=round(elapsed, 1),
            truncated=len(rows) >= self._max_rows,
        )

    async def ping(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


async def _load_date_coverage(
    conn: AsyncConnection, col_rows: Sequence[Row[Any]]
) -> tuple[DateCoverage, ...]:
    """MIN/MAX of every date column, so agents resolve "last 6 months" against the data
    rather than the wall clock (the sample warehouse is a historical snapshot)."""
    coverage: list[DateCoverage] = []
    for schema, table, column, col_type in col_rows:
        if not str(col_type).lower().startswith(DATE_TYPES):
            continue
        col = _quote_ident(column)
        source = f"{_quote_ident(schema)}.{_quote_ident(table)}"
        # Identifiers come from information_schema (not user input) and are backtick-quoted.
        query = text(f"SELECT MIN({col}), MAX({col}) FROM {source}")  # noqa: S608
        earliest, latest = (await conn.execute(query)).one()
        if earliest is not None and latest is not None:
            coverage.append(
                DateCoverage(f"{schema}.{table}.{column}", _as_date(earliest), _as_date(latest))
            )
    return tuple(coverage)


def _quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _as_date(value: dt.date | dt.datetime) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


def _describe_db_error(e: Exception) -> str:
    """Turn a driver exception into a short message without leaking connection details."""
    orig = getattr(e, "orig", None)
    args: tuple[Any, ...] = tuple(getattr(orig, "args", ()))
    if len(args) >= 2 and isinstance(args[1], str):
        code = args[0]
        if code == 3024:  # ER_QUERY_TIMEOUT
            return "The query took too long and was cancelled."
        return f"Database error {code}: {args[1]}"
    return "The database could not run this query."
