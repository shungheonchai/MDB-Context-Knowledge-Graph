import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = os.getenv("CONTEXT_KNOWLEDGE_GRAPH_MONGODB_URI", "")
    database: str = os.getenv("CONTEXT_KNOWLEDGE_GRAPH_DATABASE", "context_knowledge_graph_demo")
    lexical_index: str = os.getenv(
        "CONTEXT_KNOWLEDGE_GRAPH_LEXICAL_INDEX", "context_knowledge_graph_rules_lexical"
    )
    llm_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "GPT-6.1-Sol")
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://grove-gateway-prod.azure-api.net/grove-foundry-prod/openai/v1"
    )
    llm_auth_header: str = os.getenv("LLM_AUTH_HEADER", "api-key")
    use_llm: bool = os.getenv("CONTEXT_KNOWLEDGE_GRAPH_USE_LLM", "false").lower() == "true"
    memory_url: str = os.getenv("AGENTIC_MEMORY_BASE_URL", "")
    memory_project: str = os.getenv("AGENTIC_MEMORY_PROJECT_ID", "")
    memory_token: str = os.getenv("AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN", "")
    demo_mode: bool = os.getenv("CONTEXT_KNOWLEDGE_GRAPH_DEMO_MODE", "true").lower() == "true"
    max_runs: int = int(os.getenv("CONTEXT_KNOWLEDGE_GRAPH_MAX_CONCURRENT_RUNS", "4"))
    run_timeout: int = int(os.getenv("CONTEXT_KNOWLEDGE_GRAPH_RUN_TIMEOUT_SECONDS", "180"))
    enable_context_writes: bool = (
        os.getenv("CONTEXT_KNOWLEDGE_GRAPH_CONTEXT_WRITES", "true").lower() == "true"
    )
