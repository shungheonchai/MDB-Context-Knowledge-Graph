import asyncio
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .events import Execution
from .explorer import router as explorer_router
from .llm import create_llm
from .memory import OptionalMemory
from .models import DOMAINS, Principal, Question, now
from .repository import Repository, plain
from .scenarios import available_scenarios, resolve_scenario
from .workflow import AGENT_CATALOG, build_workflow

log = logging.getLogger(__name__)


def create_app(settings=None, repository=None, memory=None, model=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if not settings.demo_mode:
            raise RuntimeError(
                "This release serves synthetic demo data only; configure real identity before disabling demo mode"
            )
        app.state.repo = repository or Repository(settings)
        app.state.memory = memory or OptionalMemory(settings)
        built = create_llm(settings) if model is None else None
        app.state.llm = model or (built[0] if built else None)
        app.state.client = built[1] if built else None
        app.state.capacity = asyncio.Semaphore(settings.max_runs)
        app.state.active_sessions = set()
        try:
            yield
        finally:
            app.state.repo.close()
            app.state.memory.close()
            if app.state.client:
                await app.state.client.aclose()

    app = FastAPI(title="Context Knowledge Graph Pipeline Workbench", lifespan=lifespan)
    app.include_router(explorer_router)

    async def principal():
        # The accepted single-project demo deliberately permits all synthetic domains.
        # Do not accept user/client identity from natural-language requests or caller-supplied headers.
        return Principal(user_id="demo-user", client_id="synthetic-demo")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "runtime": "langgraph-custom", "demo_only": True}

    @app.get("/api/config")
    async def config(user=Depends(principal)):
        return {
            "agents": AGENT_CATALOG,
            "domains": list(DOMAINS),
            "model": settings.llm_model,
            "llm_enabled": settings.use_llm,
            "memory": "configured-unverified"
            if settings.memory_url or settings.memory_project
            else "not_configured",
            "writes": settings.enable_context_writes,
            "database": settings.database,
            "time": now(),
        }

    @app.get("/api/claims")
    async def claims(user=Depends(principal)):
        return {"claims": [str(row["_id"]) for row in await app.state.repo.list_claims()]}

    @app.get("/api/scenarios")
    async def scenarios(user=Depends(principal)):
        ids = [str(row["_id"]) for row in await app.state.repo.list_claims()]
        return {"scenarios": available_scenarios(ids), "default_scenario": "P02"}

    @app.post("/api/investigate/stream")
    async def investigate(question: Question, request: Request, user=Depends(principal)):
        try:
            resolve_scenario(question.scenario_id)
        except ValueError:
            raise HTTPException(400, "Unknown pricing scenario") from None
        session_id = question.session_id or uuid4().hex
        if session_id in app.state.active_sessions:
            raise HTTPException(409, "This session already has an active investigation")
        if app.state.capacity.locked():
            raise HTTPException(429, "Investigation capacity reached; retry shortly")
        await app.state.capacity.acquire()
        app.state.active_sessions.add(session_id)
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        run_id = uuid4().hex
        ex = Execution(
            run_id,
            session_id,
            user,
            emit=lambda event: loop.call_soon_threadsafe(queue.put_nowait, event),
        )

        async def run():
            try:
                ex.event("run", "coordinator", status="running", session_id=session_id)
                graph = build_workflow(app.state.repo, app.state.memory, ex, app.state.llm)
                async with asyncio.timeout(settings.run_timeout):
                    result = await graph.ainvoke(
                        {"question": question.question, "scenario_id": question.scenario_id}
                    )
                ex.event(
                    "answer",
                    "coordinator",
                    status="completed",
                    answer=result["answer"],
                    findings=result.get("findings", []),
                    evidence=[e.model_dump() for e in ex.evidence.values()],
                )
                ex.event("run", "coordinator", status="completed", session_id=session_id)
            except asyncio.CancelledError:
                ex.event("run", "coordinator", status="cancelled")
                raise
            except Exception as exc:
                # Never send raw connection/provider exceptions that may contain credentials.
                log.warning("Context Knowledge Graph run %s failed: %s", run_id, type(exc).__name__)
                ex.event(
                    "run",
                    "coordinator",
                    status="failed",
                    error_type=type(exc).__name__,
                    message="Investigation failed. Check local configuration and service readiness; partial context writes may have completed.",
                )
            finally:
                await asyncio.sleep(0)
                await queue.put(None)

        async def stream():
            task = asyncio.create_task(run())
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield json.dumps(plain(event)) + "\n"
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                app.state.active_sessions.discard(session_id)
                app.state.capacity.release()

        return StreamingResponse(
            stream(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/legacy", include_in_schema=False)
    async def legacy():
        from fastapi.responses import FileResponse

        return FileResponse(ROOT / "web" / "dist" / "index.html")

    web = ROOT / "web" / "dist"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()
