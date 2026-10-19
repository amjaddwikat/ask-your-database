from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator

from app.agents.base import Agent, render_rows
from app.db.warehouse import QueryResult
from app.llm.client import complete_structured


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "pie", "scatter"]
    x: str
    y: str
    group_by: str | None = None
    x_label: str
    y_label: str
    title: str

    @field_validator("x", "y", "group_by")
    @classmethod
    def _column_exists(cls, value: str | None, info: ValidationInfo) -> str | None:
        columns: list[str] = (info.context or {}).get("columns", [])
        if value is not None and columns and value not in columns:
            raise ValueError(f"'{value}' is not one of the result columns {columns}")
        return value


class PlotAgent(Agent):
    """Chooses a chart specification for a query result; the frontend renders it."""

    prompt_name = "plot"

    async def chart(self, question: str, result: QueryResult) -> ChartSpec:
        user = (
            f"User question: {question}\n\n"
            f"Result columns: {result.columns}\n"
            f"Sample rows:\n{render_rows(result.columns, result.rows, max_rows=20)}"
        )
        # Validating against the real columns means a chart can never point at a missing
        # field; if the model picks one, it is asked again with the error.
        return await complete_structured(
            self._llm,
            self.system_prompt(),
            user,
            ChartSpec,
            context={"columns": result.columns},
        )
