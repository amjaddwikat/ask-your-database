import contextvars
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.analysis import AnalysisAgent
from app.agents.plot import PlotAgent
from app.agents.router import RouterAgent
from app.agents.sql import SqlAgent
from app.api import router as api_router
from app.config import Settings, get_settings
from app.db.memory import ConversationStore
from app.db.warehouse import Warehouse, create_warehouse_engine
from app.llm.client import GeminiClient, LLMClient, LLMError
from app.orchestrator import Orchestrator

logger = logging.getLogger("app")


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    warehouse: Warehouse | None = None,
    memory: ConversationStore | None = None,
) -> FastAPI:
    """App factory. Anything not passed in is built from settings; tests inject fakes."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
    )
    _install_request_id_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as cleanup:
            wh = warehouse
            if wh is None:
                wh_engine = create_warehouse_engine(
                    settings.warehouse_url.get_secret_value(), settings.query_timeout_ms
                )
                cleanup.push_async_callback(wh_engine.dispose)
                wh = Warehouse(wh_engine, max_rows=settings.max_result_rows)
                await wh.load_schema(settings.warehouse_schemas)

            mem = memory
            if mem is None:
                app_engine = create_async_engine(
                    settings.app_db_url.get_secret_value(), pool_pre_ping=True
                )
                cleanup.push_async_callback(app_engine.dispose)
                mem = ConversationStore(app_engine, window=settings.history_window)
                await mem.create_tables()

            client = llm
            if client is None:
                gemini = GeminiClient(
                    settings.gemini_api_key.get_secret_value(),
                    settings.gemini_model,
                    timeout_s=settings.llm_timeout_s,
                )
                cleanup.push_async_callback(gemini.aclose)
                client = gemini

            app.state.settings = settings
            app.state.warehouse = wh
            app.state.memory = mem
            app.state.orchestrator = Orchestrator(
                RouterAgent(client),
                SqlAgent(client),
                AnalysisAgent(client),
                PlotAgent(client),
                wh,
                mem,
            )
            yield

    app = FastAPI(
        title="Ask Your Database",
        version="0.1.0",
        description="Multi-agent natural-language interface to a SQL data warehouse.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.middleware("http")(_request_id_middleware)
    _register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"], summary="Readiness probe (checks the warehouse)")
    async def ready(request: Request) -> JSONResponse:
        try:
            await request.app.state.warehouse.ping()
        except Exception:
            logger.exception("Readiness check failed")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    return app


# --- request ids -------------------------------------------------------------------------

_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def _install_request_id_logging() -> None:
    """Make every log line carry the id of the request that produced it."""
    old_factory = logging.getLogRecordFactory()
    if getattr(old_factory, "_adds_request_id", False):
        return

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.request_id = _current_request_id.get()
        return record

    factory._adds_request_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


async def _request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    token = _current_request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _current_request_id.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


# --- errors ------------------------------------------------------------------------------


def _error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request_id}},
        status_code=status_code,
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []))
        return _error(request, 422, "invalid_request", f"{where}: {first.get('msg', 'invalid')}")

    @app.exception_handler(LLMError)
    async def llm_error(request: Request, exc: LLMError) -> JSONResponse:
        logger.warning("LLM failure: %s", exc)
        return _error(
            request,
            502,
            "llm_unavailable",
            "The language model is unavailable right now. Please try again.",
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _error(request, 500, "internal_error", "Something went wrong on our side.")
