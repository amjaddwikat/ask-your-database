from typing import Literal, Self

from pydantic import BaseModel, model_validator

from app.agents.base import Agent
from app.llm.client import complete_structured

Action = Literal["analysis", "plot", "general", "blocked"]


class RouterDecision(BaseModel):
    action: Action
    rephrased_question: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def _fields_match_action(self) -> Self:
        if self.action in ("analysis", "plot") and not self.rephrased_question:
            raise ValueError("rephrased_question is required for analysis/plot")
        if self.action in ("general", "blocked") and not self.message:
            raise ValueError("message is required for general/blocked")
        return self


class RouterAgent(Agent):
    """Validates the request and decides which pipeline (if any) should handle it."""

    prompt_name = "router"

    async def decide(self, question: str, schema: str, history: str) -> RouterDecision:
        system = self.system_prompt(schema=schema, history=history)
        return await complete_structured(
            self._llm, system, f"User message: {question}", RouterDecision
        )
