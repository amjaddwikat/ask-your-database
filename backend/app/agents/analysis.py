from app.agents.base import Agent, render_rows
from app.db.warehouse import QueryResult


class AnalysisAgent(Agent):
    """Explains a query result in plain language, grounded only in the returned rows."""

    prompt_name = "analysis"

    async def analyze(self, question: str, result: QueryResult, time_context: str) -> str:
        user = (
            f"User question: {question}\n\n"
            f"SQL that was run:\n{result.sql}\n\n"
            f"Result ({result.row_count} rows{', truncated' if result.truncated else ''}):\n"
            f"{render_rows(result.columns, result.rows)}"
        )
        text = await self._llm.complete(self.system_prompt(time_context=time_context), user)
        return text.strip()
