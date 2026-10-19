from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from app.agents.analysis import AnalysisAgent
from app.agents.plot import PlotAgent
from app.agents.router import RouterAgent
from app.agents.sql import SqlAgent
from app.config import Settings
from app.db.memory import ConversationStore
from app.main import create_app
from app.orchestrator import Orchestrator
from tests.fakes import FakeLLM, FakeWarehouse

API_KEY = "test-key"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key=SecretStr(API_KEY),
        warehouse_url=SecretStr("mysql+aiomysql://unused/unused"),
        app_db_url=SecretStr("sqlite+aiosqlite://"),
        gemini_api_key=SecretStr("unused"),
        _env_file=None,
    )


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def warehouse() -> FakeWarehouse:
    return FakeWarehouse(rows=[{"ContractType": "Monthly", "avg_age": 41.2}])


@pytest.fixture
async def memory() -> AsyncIterator[ConversationStore]:
    # A real SQL database (in-memory SQLite) so the memory queries are actually exercised.
    engine = create_async_engine("sqlite+aiosqlite://")
    store = ConversationStore(engine, window=10)
    await store.create_tables()
    yield store
    await engine.dispose()


@pytest.fixture
def orchestrator(llm: FakeLLM, warehouse: FakeWarehouse, memory: ConversationStore) -> Orchestrator:
    return Orchestrator(
        RouterAgent(llm), SqlAgent(llm), AnalysisAgent(llm), PlotAgent(llm), warehouse, memory
    )


@pytest.fixture
def client(
    settings: Settings, llm: FakeLLM, warehouse: FakeWarehouse, memory: ConversationStore
) -> Iterator[TestClient]:
    app = create_app(settings, llm=llm, warehouse=warehouse, memory=memory)
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c
