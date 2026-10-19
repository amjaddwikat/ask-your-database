"""Runs against the real MySQL from docker-compose.

    docker compose up -d mysql
    WAREHOUSE_URL=mysql+aiomysql://warehouse_ro:<password>@localhost:3306/telecom_dw \
        pytest -m integration
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from app.db.warehouse import QueryExecutionError, Warehouse, create_warehouse_engine

pytestmark = pytest.mark.integration


@pytest.fixture
async def warehouse() -> AsyncIterator[Warehouse]:
    url = os.environ.get("WAREHOUSE_URL")
    if not url:
        pytest.skip("WAREHOUSE_URL not set")
    engine = create_warehouse_engine(url, query_timeout_ms=1000)
    wh = Warehouse(engine, max_rows=500)
    await wh.load_schema(["telecom_dw"])
    yield wh
    await engine.dispose()


async def test_schema_is_introspected_with_foreign_keys(warehouse: Warehouse) -> None:
    assert warehouse.schema is not None
    assert warehouse.schema.table_names == {
        "telecom_dw.dimcustomer",
        "telecom_dw.dimdate",
        "telecom_dw.dimservice",
        "telecom_dw.factbilling",
    }
    described = warehouse.schema.describe()
    assert "telecom_dw.factbilling.CustomerID -> telecom_dw.dimcustomer.CustomerID" in described


async def test_runs_an_analytical_query(warehouse: Warehouse) -> None:
    result = await warehouse.run(
        "SELECT c.ContractType, ROUND(AVG(f.LatePaymentFlag) * 100, 1) AS late_pct "
        "FROM telecom_dw.factbilling f JOIN telecom_dw.dimcustomer c "
        "ON f.CustomerID = c.CustomerID GROUP BY c.ContractType ORDER BY late_pct DESC"
    )
    assert result.columns == ["ContractType", "late_pct"]
    assert {r["ContractType"] for r in result.rows} == {"Monthly", "One year", "Two year"}
    assert isinstance(result.rows[0]["late_pct"], float)  # Decimal converted for JSON
    assert result.rows[0]["ContractType"] == "Monthly"  # the story baked into the seed data


async def test_like_with_percent_signs_works(warehouse: Warehouse) -> None:
    result = await warehouse.run(
        "SELECT COUNT(*) AS n FROM telecom_dw.dimcustomer WHERE City LIKE '%lus%'"
    )
    assert result.rows[0]["n"] > 0


async def test_database_user_cannot_write_even_if_guard_is_bypassed(
    warehouse: Warehouse,
) -> None:
    # Go straight to the engine, skipping the QueryGuard, to prove the DB layer holds too.
    with pytest.raises(Exception, match=r"(?i)denied|read only|read-only"):
        async with warehouse._engine.begin() as conn:
            await conn.execute(text("DELETE FROM telecom_dw.dimcustomer WHERE CustomerID = 1"))


async def test_sessions_are_hardened(warehouse: Warehouse) -> None:
    result = await warehouse.run(
        "SELECT @@SESSION.max_execution_time AS timeout_ms, "
        "@@SESSION.transaction_read_only AS read_only"
    )
    assert result.rows == [{"timeout_ms": 1000, "read_only": 1}]


async def test_slow_queries_are_cancelled(warehouse: Warehouse) -> None:
    # ~92M joined rows with real arithmetic: far longer than the 1s MAX_EXECUTION_TIME.
    with pytest.raises(QueryExecutionError, match="too long"):
        await warehouse.run(
            "SELECT SUM(a.BillAmount * b.UsageMinutes) AS x FROM telecom_dw.factbilling a "
            "CROSS JOIN telecom_dw.factbilling b WHERE a.BillAmount + b.BillAmount > 0"
        )
