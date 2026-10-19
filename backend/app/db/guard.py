"""Static validation of LLM-generated SQL before it reaches the database.

The model's output is treated as untrusted input. A query is only executed if it is a
single read-only SELECT over an allow-listed set of tables, and every query gets a row
limit. This is one layer of defence; the database user is also read-only and every
statement runs with a server-side timeout (see warehouse.py).
"""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# Statement types that must never appear anywhere in the tree (including subqueries/CTEs).
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Drop",
    "Create",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Command",
    "Into",
    "Lock",
    "Set",
    "Grant",
    "Use",
    "Transaction",
    "Commit",
    "Rollback",
    "LoadData",
    "Copy",
)
_FORBIDDEN_NODES = tuple(getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name))

# Functions that can read files, stall the server, or take locks.
_FORBIDDEN_FUNCTIONS = {
    "SLEEP",
    "BENCHMARK",
    "LOAD_FILE",
    "GET_LOCK",
    "RELEASE_LOCK",
    "RELEASE_ALL_LOCKS",
    "IS_FREE_LOCK",
    "IS_USED_LOCK",
    "MASTER_POS_WAIT",
    "SOURCE_POS_WAIT",
    "SYS_EXEC",
    "SYS_EVAL",
}

# Belt and braces for MySQL syntax the parser may not model as a distinct node.
_FORBIDDEN_TEXT = re.compile(r"\binto\s+(outfile|dumpfile)\b", re.IGNORECASE)


class UnsafeQueryError(ValueError):
    """Raised when generated SQL is rejected. The message is safe to show to users."""


class QueryGuard:
    def __init__(
        self,
        allowed_tables: set[str],
        default_schema: str,
        max_rows: int,
        dialect: str = "mysql",
    ) -> None:
        # Table names are compared case-insensitively as "schema.table".
        self._allowed = {t.lower() for t in allowed_tables}
        self._default_schema = default_schema.lower()
        self._max_rows = max_rows
        self._dialect = dialect

    def validate(self, sql: str) -> str:
        """Return a normalised, row-limited version of `sql`, or raise UnsafeQueryError."""
        if not sql or not sql.strip():
            raise UnsafeQueryError("The query is empty.")
        if _FORBIDDEN_TEXT.search(sql):
            raise UnsafeQueryError("Writing query results to files is not allowed.")

        try:
            statements = [s for s in sqlglot.parse(sql, read=self._dialect) if s is not None]
        except ParseError as e:
            raise UnsafeQueryError("The generated SQL could not be parsed.") from e

        if len(statements) != 1:
            raise UnsafeQueryError("Exactly one SQL statement is allowed.")
        stmt = statements[0]

        if not isinstance(stmt, exp.Query):
            raise UnsafeQueryError("Only SELECT queries are allowed.")

        for node in stmt.walk():
            if isinstance(node, _FORBIDDEN_NODES):
                raise UnsafeQueryError(f"{type(node).__name__.upper()} operations are not allowed.")
            if isinstance(node, exp.Func) and self._function_name(node) in _FORBIDDEN_FUNCTIONS:
                raise UnsafeQueryError(f"The function {self._function_name(node)} is not allowed.")

        self._check_tables(stmt)
        return self._apply_row_limit(stmt).sql(dialect=self._dialect)

    @staticmethod
    def _function_name(node: exp.Func) -> str:
        if isinstance(node, exp.Anonymous):
            return str(node.name).upper()
        return str(node.sql_name()).upper()  # type: ignore[no-untyped-call]

    def _check_tables(self, stmt: exp.Expression) -> None:
        cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
        for table in stmt.find_all(exp.Table):
            name = table.name.lower()
            schema = (table.db or "").lower()
            if not schema and name in cte_names:
                continue
            qualified = f"{schema or self._default_schema}.{name}"
            if qualified not in self._allowed:
                raise UnsafeQueryError(f"Access to table '{qualified}' is not allowed.")

    def _apply_row_limit(self, stmt: exp.Query) -> exp.Query:
        limit = stmt.args.get("limit")
        if limit is None:
            return stmt.limit(self._max_rows)
        value = limit.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.this) <= self._max_rows:
            return stmt
        # Non-literal or too-large limits are clamped.
        return stmt.limit(self._max_rows)
