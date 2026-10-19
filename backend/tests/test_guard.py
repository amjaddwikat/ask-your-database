import pytest

from app.db.guard import QueryGuard, UnsafeQueryError

ALLOWED = {"telecom_dw.dimcustomer", "telecom_dw.factbilling", "telecom_dw.dimdate"}


@pytest.fixture
def guard() -> QueryGuard:
    return QueryGuard(ALLOWED, default_schema="telecom_dw", max_rows=500)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ContractType, AVG(Age) AS avg_age FROM telecom_dw.dimcustomer "
        "GROUP BY ContractType",
        "SELECT * FROM dimcustomer",  # unqualified tables resolve to the default schema
        "SELECT c.Region, COUNT(*) FROM telecom_dw.factbilling f "
        "JOIN telecom_dw.dimcustomer c ON f.CustomerID = c.CustomerID GROUP BY c.Region",
        "WITH big AS (SELECT CustomerID FROM telecom_dw.factbilling WHERE BillAmount > 100) "
        "SELECT COUNT(*) FROM big",
        "SELECT 1 FROM dimcustomer UNION ALL SELECT 2 FROM factbilling",
        "SELECT * FROM (SELECT Age FROM dimcustomer) AS t",
        "SELECT * FROM dimcustomer WHERE City LIKE '%Nablus%'",
    ],
)
def test_allows_read_only_queries(guard: QueryGuard, sql: str) -> None:
    assert guard.validate(sql).upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DROP TABLE telecom_dw.dimcustomer", "Only SELECT"),
        ("DELETE FROM dimcustomer", "Only SELECT"),
        ("UPDATE dimcustomer SET Age = 0", "Only SELECT"),
        ("INSERT INTO dimcustomer SELECT * FROM dimcustomer", "Only SELECT"),
        ("TRUNCATE TABLE dimcustomer", "Only SELECT"),
        ("SET GLOBAL max_connections = 1", "Only SELECT"),
        ("SELECT 1; DROP TABLE dimcustomer", "Exactly one"),
        ("SELECT * FROM mysql.user", "not allowed"),
        ("SELECT * FROM information_schema.tables", "not allowed"),
        ("SELECT * FROM dimcustomer WHERE CustomerID IN (SELECT id FROM other.t)", "not allowed"),
        ("SELECT SLEEP(10)", "SLEEP"),
        ("SELECT BENCHMARK(1000000, MD5('a'))", "BENCHMARK"),
        ("SELECT LOAD_FILE('/etc/passwd')", "LOAD_FILE"),
        ("SELECT * FROM dimcustomer INTO OUTFILE '/tmp/x'", "files"),
        ("SELECT * FROM dimcustomer FOR UPDATE", "LOCK"),
        ("", "empty"),
        ("this is not sql", "parsed|Only SELECT"),
    ],
)
def test_rejects_unsafe_queries(guard: QueryGuard, sql: str, reason: str) -> None:
    with pytest.raises(UnsafeQueryError, match=reason):
        guard.validate(sql)


def test_adds_limit_when_missing(guard: QueryGuard) -> None:
    assert guard.validate("SELECT * FROM dimcustomer").endswith("LIMIT 500")


def test_keeps_smaller_limit(guard: QueryGuard) -> None:
    assert guard.validate("SELECT * FROM dimcustomer LIMIT 10").endswith("LIMIT 10")


def test_clamps_larger_limit(guard: QueryGuard) -> None:
    assert guard.validate("SELECT * FROM dimcustomer LIMIT 100000").endswith("LIMIT 500")


def test_cte_names_are_not_treated_as_tables(guard: QueryGuard) -> None:
    sql = "WITH secret AS (SELECT Age FROM dimcustomer) SELECT * FROM secret"
    assert "secret" in guard.validate(sql)
