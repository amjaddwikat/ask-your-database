"""Runs the agent pipeline for one user message.

user message
    -> RouterAgent  -- general / blocked --> reply directly
    -> SqlAgent -> QueryGuard -> Warehouse   (one repair attempt on failure)
    -> AnalysisAgent  (+ PlotAgent in parallel for chart requests)
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.agents.analysis import AnalysisAgent
from app.agents.plot import ChartSpec, PlotAgent
from app.agents.router import RouterAgent
from app.agents.sql import SqlAgent, SqlDraft
from app.db.guard import UnsafeQueryError
from app.db.memory import ConversationStore, format_history
from app.db.warehouse import QueryExecutionError, QueryResult, Warehouse
from app.llm.client import LLMError
from app.schemas import Chart, ChatResponse, QueryData, StepTrace

logger = logging.getLogger(__name__)

ROWS_RETURNED_TO_CLIENT = 200


class _Trace:
    def __init__(self) -> None:
        self.steps: list[StepTrace] = []

    @asynccontextmanager
    async def step(self, name: str, detail: str | None = None) -> AsyncIterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            self.steps.append(StepTrace(step=name, duration_ms=elapsed, detail=detail))


class Orchestrator:
    def __init__(
        self,
        router: RouterAgent,
        sql_agent: SqlAgent,
        analysis_agent: AnalysisAgent,
        plot_agent: PlotAgent,
        warehouse: Warehouse,
        memory: ConversationStore,
        max_sql_attempts: int = 2,
    ) -> None:
        self._router = router
        self._sql = sql_agent
        self._analysis = analysis_agent
        self._plot = plot_agent
        self._warehouse = warehouse
        self._memory = memory
        self._max_sql_attempts = max_sql_attempts

    async def handle(self, session_id: str, question: str) -> ChatResponse:
        trace = _Trace()
        history = format_history(await self._memory.recent(session_id))
        assert self._warehouse.schema is not None, "warehouse schema not loaded"
        schema = self._warehouse.schema.describe()

        async with trace.step("router"):
            decision = await self._router.decide(question, schema, history)
        trace.steps[-1].detail = decision.action

        if decision.action in ("general", "blocked"):
            response = ChatResponse(
                session_id=session_id,
                type=decision.action,
                message=decision.message or "",
                trace=trace.steps,
            )
            await self._remember(session_id, question, response)
            return response

        rephrased = decision.rephrased_question or question
        outcome = await self._query_with_repair(rephrased, schema, history, trace)
        if isinstance(outcome, ChatResponse):
            outcome.session_id = session_id
            await self._remember(session_id, question, outcome)
            return outcome
        draft, result = outcome

        chart: Chart | None = None
        if decision.action == "plot" and result.rows:
            async with trace.step("analysis+plot", detail="parallel"):
                analysis, spec = await asyncio.gather(
                    self._analysis.analyze(rephrased, result),
                    self._safe_chart(rephrased, result),
                )
            if spec is not None:
                chart = Chart(spec=spec, data=result.rows[:ROWS_RETURNED_TO_CLIENT])
            else:
                analysis += "\n\n_I couldn't build a chart for this result._"
        else:
            async with trace.step("analysis"):
                analysis = await self._analysis.analyze(rephrased, result)

        response = ChatResponse(
            session_id=session_id,
            type="plot" if chart else "analysis",
            message=analysis,
            query=QueryData(
                sql=result.sql,
                explanation=draft.explanation,
                columns=result.columns,
                rows=result.rows[:ROWS_RETURNED_TO_CLIENT],
                row_count=result.row_count,
                truncated=result.truncated or result.row_count > ROWS_RETURNED_TO_CLIENT,
            ),
            chart=chart,
            trace=trace.steps,
        )
        await self._remember(session_id, question, response)
        return response

    async def _query_with_repair(
        self, question: str, schema: str, history: str, trace: _Trace
    ) -> tuple[SqlDraft, QueryResult] | ChatResponse:
        """Generate and run SQL; if the guard or database rejects it, let the model fix it."""
        previous: tuple[str, str] | None = None
        for attempt in range(1, self._max_sql_attempts + 1):
            async with trace.step("sql", detail=f"attempt {attempt}"):
                draft = await self._sql.generate(question, schema, history, previous)
            if not draft.sql:
                return ChatResponse(
                    session_id="",
                    type="clarification",
                    message=draft.explanation,
                    trace=trace.steps,
                )
            try:
                async with trace.step("warehouse"):
                    result = await self._warehouse.run(draft.sql)
                trace.steps[-1].detail = f"{result.row_count} rows"
                return draft, result
            except (UnsafeQueryError, QueryExecutionError) as e:
                trace.steps[-1].detail = f"rejected: {e}"
                logger.info("SQL attempt %d failed: %s", attempt, e)
                previous = (draft.sql, str(e))

        assert previous is not None
        return ChatResponse(
            session_id="",
            type="error",
            message=(
                "I couldn't produce a valid query for that question. "
                f"The last problem was: {previous[1]} Try rephrasing or narrowing the question."
            ),
            trace=trace.steps,
        )

    async def _safe_chart(self, question: str, result: QueryResult) -> ChartSpec | None:
        # A failed chart shouldn't throw away a good analysis.
        try:
            return await self._plot.chart(question, result)
        except LLMError as e:
            logger.warning("Plot agent failed: %s", e)
            return None

    async def _remember(self, session_id: str, question: str, response: ChatResponse) -> None:
        content = response.message
        if response.query:
            # Keeping the SQL in memory lets follow-ups like "same, but for 2024" work.
            content += f"\n\n[SQL used: {response.query.sql}]"
        await self._memory.append(session_id, "user", question)
        await self._memory.append(session_id, "assistant", content)
