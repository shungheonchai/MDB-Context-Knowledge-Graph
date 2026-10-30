import asyncio
from typing import Protocol

from .models import now


class MemoryPort(Protocol):
    async def recall(self, execution, agent: str, query: str) -> str: ...
    async def record(self, execution, agent: str, role: str, content: str) -> None: ...


class OptionalMemory:
    """Only this adapter knows about Atlas Agent Engine; no hosted agent runtime imports."""

    def __init__(self, settings):
        self.settings = settings
        self.client = None
        if settings.memory_url or settings.memory_project:
            from agent_engine_sdk_memory import Memory

            if settings.memory_project and not settings.memory_token:
                raise RuntimeError("Hosted memory requires AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN")
            args = {}
            if settings.memory_url:
                args["base_url"] = settings.memory_url
            if settings.memory_project:
                args.update(
                    project_id=settings.memory_project, service_account_token=settings.memory_token
                )
            self.client = Memory(**args)

    def scoped(self, execution, agent):
        from agent_engine_sdk_memory import MemoryRequestContext

        # Owner identity includes the agent, so even user-only server filtering isolates agents.
        # Scope is derived from authenticated server identity, not model-generated arguments.
        identity = ":".join([execution.principal.client_id, execution.principal.user_id, agent])
        return self.client.bind(
            MemoryRequestContext(user_id=identity, agent_id=agent, session_id=execution.session_id)
        )

    async def recall(self, execution, agent, query):
        if self.client is None:
            execution.event("memory", agent, status="not_configured")
            return ""
        try:
            session = self.scoped(execution, agent)
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    session.build_context,
                    query=query,
                    enabled_sources={"semantic", "episodic", "taxonomic", "procedural"},
                    max_tokens=1600,
                ),
                timeout=15,
            )
            text = getattr(result, "formatted_context", result)
            execution.event("memory", agent, status="read", observed_at=now())
            return text if isinstance(text, str) else ""
        except Exception as exc:
            execution.event("memory", agent, status="unavailable", error_type=type(exc).__name__)
            return ""

    async def record(self, execution, agent, role, content):
        if self.client is None:
            return
        try:
            session = self.scoped(execution, agent)
            await asyncio.wait_for(
                asyncio.to_thread(session.record_turn, role=role, content=content), timeout=15
            )
            execution.event("memory", agent, status="written")
        except Exception as exc:
            execution.event("memory", agent, status="unavailable", error_type=type(exc).__name__)

    def close(self):
        if self.client is not None:
            close = getattr(self.client, "close", None)
            if close:
                close()
