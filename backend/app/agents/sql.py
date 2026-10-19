from pydantic import BaseModel

from app.agents.base import Agent
from app.llm.client import complete_structured


class SqlDraft(BaseModel):
    sql: str
    explanation: str


class SqlAgent(Agent):
    """Translates a self-contained question into a single MySQL SELECT."""

    prompt_name = "sql"

    async def generate(
        self,
        question: str,
        schema: str,
        history: str,
        previous_attempt: tuple[str, str] | None = None,
    ) -> SqlDraft:
        user = f"Question: {question}"
        if previous_attempt:
            failed_sql, error = previous_attempt
            user += (
                f"\n\nYour previous query failed and must be fixed.\n"
                f"Query:\n{failed_sql}\nError:\n{error}"
            )
        system = self.system_prompt(schema=schema, history=history)
        draft = await complete_structured(self._llm, system, user, SqlDraft)
        draft.sql = draft.sql.strip().rstrip(";").strip()
        return draft
