import datetime as dt

from app.db.warehouse import DateCoverage, WarehouseSchema


def test_latest_date_is_the_most_recent_across_date_columns() -> None:
    schema = WarehouseSchema(
        tables=(),
        date_coverage=(
            DateCoverage("dw.dimcustomer.JoinDate", dt.date(2019, 1, 1), dt.date(2023, 12, 30)),
            DateCoverage("dw.dimdate.FullDate", dt.date(2024, 1, 1), dt.date(2025, 12, 1)),
        ),
    )

    assert schema.latest_date == dt.date(2025, 12, 1)
    assert 'Treat 2025-12-01 as "today"' in schema.time_context()
    assert "- dw.dimdate.FullDate: 2024-01-01 to 2025-12-01" in schema.describe()


def test_schema_without_dates_has_no_reference_date() -> None:
    schema = WarehouseSchema(tables=())

    assert schema.latest_date is None
    assert "Date coverage" not in schema.describe()
    assert schema.time_context() == "No date range is known for this data."
