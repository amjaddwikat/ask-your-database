from app.db.memory import ConversationStore
from app.orchestrator import Orchestrator
from tests.fakes import FakeLLM, FakeWarehouse

ROUTE_ANALYSIS = {"action": "analysis", "rephrased_question": "Average age per contract type"}
ROUTE_PLOT = {"action": "plot", "rephrased_question": "Chart average age per contract type"}
GOOD_SQL = {
    "sql": "SELECT ContractType, AVG(Age) AS avg_age FROM telecom_dw.dimcustomer "
    "GROUP BY ContractType;",
    "explanation": "Averages customer age per contract type.",
}
CHART = {
    "chart_type": "bar",
    "x": "ContractType",
    "y": "avg_age",
    "group_by": None,
    "x_label": "Contract type",
    "y_label": "Average age",
    "title": "Average age by contract",
}


async def test_general_message_skips_the_data_pipeline(
    orchestrator: Orchestrator, llm: FakeLLM, warehouse: FakeWarehouse
) -> None:
    llm.reply("router", {"action": "general", "message": "Hi! Ask me about your customers."})

    response = await orchestrator.handle("session-1", "hello")

    assert response.type == "general"
    assert response.message.startswith("Hi!")
    assert warehouse.executed == []
    assert [s.step for s in response.trace] == ["router"]


async def test_blocked_request_never_reaches_sql_agent(
    orchestrator: Orchestrator, llm: FakeLLM
) -> None:
    llm.reply("router", {"action": "blocked", "message": "I can't delete data."})

    response = await orchestrator.handle("session-1", "delete all customers")

    assert response.type == "blocked"
    assert llm.calls_to("sql") == []


async def test_analysis_flow_runs_sql_and_explains_result(
    orchestrator: Orchestrator, llm: FakeLLM, warehouse: FakeWarehouse
) -> None:
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", GOOD_SQL)
    llm.reply("analysis", "Monthly customers average **41.2** years.")

    response = await orchestrator.handle("session-1", "avg age by contract?")

    assert response.type == "analysis"
    assert response.query is not None
    assert response.query.rows == [{"ContractType": "Monthly", "avg_age": 41.2}]
    assert response.query.sql.endswith("LIMIT 500")  # the guard's limit, trailing ';' removed
    assert response.chart is None
    assert [s.step for s in response.trace] == ["router", "sql", "warehouse", "analysis"]
    # The SQL agent gets the router's rephrased, self-contained question.
    assert "Average age per contract type" in llm.calls_to("sql")[0]


async def test_plot_flow_returns_chart_spec_and_data(
    orchestrator: Orchestrator, llm: FakeLLM
) -> None:
    llm.reply("router", ROUTE_PLOT).reply("sql", GOOD_SQL)
    llm.reply("analysis", "Here is the breakdown.").reply("plot", CHART)

    response = await orchestrator.handle("session-1", "chart it")

    assert response.type == "plot"
    assert response.chart is not None
    assert response.chart.spec.chart_type == "bar"
    assert response.chart.data == [{"ContractType": "Monthly", "avg_age": 41.2}]


async def test_unsafe_sql_is_sent_back_to_the_model_for_repair(
    orchestrator: Orchestrator, llm: FakeLLM, warehouse: FakeWarehouse
) -> None:
    bad = {"sql": "DELETE FROM telecom_dw.dimcustomer", "explanation": "oops"}
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", bad, GOOD_SQL).reply("analysis", "ok")

    response = await orchestrator.handle("session-1", "avg age by contract?")

    assert response.type == "analysis"
    assert len(warehouse.executed) == 1  # the DELETE never reached the database
    repair_prompt = llm.calls_to("sql")[1]
    assert "DELETE FROM telecom_dw.dimcustomer" in repair_prompt
    assert "Only SELECT" in repair_prompt


async def test_database_error_triggers_repair(
    orchestrator: Orchestrator, llm: FakeLLM, warehouse: FakeWarehouse
) -> None:
    warehouse.fail_with = "Database error 1054: Unknown column 'Agee'"
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", GOOD_SQL, GOOD_SQL).reply("analysis", "ok")

    response = await orchestrator.handle("session-1", "avg age?")

    assert response.type == "analysis"
    assert "Unknown column" in llm.calls_to("sql")[1]


async def test_gives_up_after_max_attempts(orchestrator: Orchestrator, llm: FakeLLM) -> None:
    bad = {"sql": "DROP TABLE telecom_dw.dimcustomer", "explanation": "x"}
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", bad, bad)

    response = await orchestrator.handle("session-1", "avg age?")

    assert response.type == "error"
    assert "couldn't produce a valid query" in response.message
    assert llm.calls_to("analysis") == []


async def test_empty_sql_means_clarification(orchestrator: Orchestrator, llm: FakeLLM) -> None:
    llm.reply("router", ROUTE_ANALYSIS)
    llm.reply("sql", {"sql": "", "explanation": "Which region do you mean?"})

    response = await orchestrator.handle("session-1", "how is my region doing")

    assert response.type == "clarification"
    assert response.message == "Which region do you mean?"


async def test_bad_chart_degrades_to_analysis(orchestrator: Orchestrator, llm: FakeLLM) -> None:
    missing_column = {**CHART, "y": "revenue"}  # not a result column
    llm.reply("router", ROUTE_PLOT).reply("sql", GOOD_SQL).reply("analysis", "Breakdown.")
    llm.reply("plot", missing_column, missing_column)

    response = await orchestrator.handle("session-1", "chart it")

    assert response.type == "analysis"
    assert response.chart is None
    assert "couldn't build a chart" in response.message


async def test_conversation_is_remembered_for_follow_ups(
    orchestrator: Orchestrator, llm: FakeLLM, memory: ConversationStore
) -> None:
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", GOOD_SQL).reply("analysis", "Answer one.")
    await orchestrator.handle("session-1", "first question")

    llm.reply("router", {"action": "general", "message": "You asked about contracts."})
    await orchestrator.handle("session-1", "what did I ask?")

    history = await memory.recent("session-1")
    assert [m.role for m in history] == ["user", "assistant", "user", "assistant"]
    assert "[SQL used:" in history[1].content
    # The second router call saw the first exchange in its prompt.
    last_router_prompt = [s for agent, s in llm.system_prompts if agent == "router"][-1]
    assert "USER: first question" in last_router_prompt


async def test_agents_resolve_relative_dates_against_the_data(
    orchestrator: Orchestrator, llm: FakeLLM
) -> None:
    llm.reply("router", ROUTE_ANALYSIS).reply("sql", GOOD_SQL).reply("analysis", "Done.")

    await orchestrator.handle("session-1", "customers who joined in the last 6 months")

    prompts = dict(llm.system_prompts)
    # The sample warehouse is a snapshot, so "today" is its latest date, not the wall clock.
    assert "most recent date is 2025-12-01" in prompts["sql"]
    assert "telecom_dw.dimcustomer.JoinDate: 2019-01-01 to 2025-12-01" in prompts["sql"]
    assert "most recent date is 2025-12-01" in prompts["analysis"]
