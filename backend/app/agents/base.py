import json
from functools import cache
from importlib import resources
from string import Template
from typing import Any

from app.llm.client import LLMClient


@cache
def load_prompt(name: str) -> Template:
    text = resources.files("app.agents.prompts").joinpath(f"{name}.md").read_text("utf-8")
    return Template(text)


def render_rows(columns: list[str], rows: list[dict[str, Any]], max_rows: int = 100) -> str:
    """Serialise result rows compactly for a prompt (one JSON object per line)."""
    if not rows:
        return f"columns: {columns}\n(no rows)"
    shown = rows[:max_rows]
    body = "\n".join(json.dumps(r, default=str, ensure_ascii=False) for r in shown)
    more = f"\n... {len(rows) - max_rows} more rows not shown" if len(rows) > max_rows else ""
    return f"columns: {columns}\n{body}{more}"


class Agent:
    prompt_name: str

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def system_prompt(self, **values: str) -> str:
        return load_prompt(self.prompt_name).substitute(**values)
