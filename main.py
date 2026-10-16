from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import Settings
from src.bots.registry import build_bot_registry
from src.context.mongo_store import MongoConversationStore
from src.llm.qwen import QwenClient
from src.orchestrator.composer import ContextComposer
from src.orchestrator.models import ChatRequest, ChatResponse, OrchestratorResult
from src.orchestrator.router import Router
from src.orchestrator.service import OrchestratorService


def create_service(
    settings: Settings | None = None,
) -> tuple[OrchestratorService, QwenClient]:
    app_settings = settings or Settings.from_env()
    llm = QwenClient(app_settings)
    bots = build_bot_registry()
    store = MongoConversationStore(
        uri=app_settings.mongodb_uri,
        database=app_settings.mongodb_database,
        collection=app_settings.mongodb_collection,
        server_selection_timeout_ms=(
            app_settings.mongodb_server_selection_timeout_ms
        ),
    )
    service = OrchestratorService(
        store=store,
        router=Router(llm, bots),
        composer=ContextComposer(llm),
        bots=bots,
    )
    return service, llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = None
    llm = None
    orchestrator = None
    try:
        service, llm = create_service()
        await service.initialize()
        orchestrator = service
        initialization_error = None
    except Exception as exc:
        initialization_error = f"{type(exc).__name__}: {exc}"
    app.state.orchestrator = orchestrator
    app.state.initialization_error = initialization_error
    yield
    if service is not None:
        await service.close()
    if llm is not None:
        await llm.close()


app = FastAPI(title="Teams Chatbot Orchestrator", lifespan=lifespan)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(static_dir / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    if request.app.state.orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.initialization_error,
        )
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    service: OrchestratorService | None = request.app.state.orchestrator
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.initialization_error,
        )
    try:
        result = await service.handle_message(
            conversation_id=payload.conversation_id,
            user_id=payload.user_id,
            message=payload.message,
            emp_id=payload.emp_id,
            emp_name=payload.emp_name,
            # Trace powers the workflow/debug UI and may contain sensitive data.
            include_trace=payload.debug,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(result, OrchestratorResult):
        return ChatResponse(response=result.response, trace=result.trace)
    return ChatResponse(response=result)
