import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def create_llm(settings):
    if not settings.use_llm:
        return None
    if not settings.llm_key:
        raise RuntimeError(
            "Set LLM_API_KEY locally, or CONTEXT_KNOWLEDGE_GRAPH_USE_LLM=false for evidence-only mode"
        )

    async def inject(request):
        request.headers.pop("authorization", None)
        value = settings.llm_key
        request.headers[settings.llm_auth_header] = (
            "Bearer " + value if settings.llm_auth_header.lower() == "authorization" else value
        )

    # A bounded request timeout prevents an unavailable gateway from holding a run indefinitely.
    client = httpx.AsyncClient(
        event_hooks={"request": [inject]}, follow_redirects=False, timeout=60
    )
    llm = ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=SecretStr("unused"),
        use_responses_api=True,
        http_async_client=client,
        max_retries=1,
    )
    return llm, client
