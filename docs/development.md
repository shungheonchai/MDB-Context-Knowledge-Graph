# Development guide

Use the [root README](../README.md) for Docker setup and environment configuration. The only local configuration file is `context-knowledge-graph-runtime/.env`; there is no root environment file. Commands below run from `context-knowledge-graph-runtime` unless specified otherwise.

## Code map

| Path within the runtime | Responsibility |
|---|---|
| `src/context_knowledge_graph/api.py` | FastAPI lifecycle, routes, shared resources, and static UI serving. |
| `src/context_knowledge_graph/explorer.py` | Studio catalog, request validation, stage plans, and streamed read-only previews. |
| `src/context_knowledge_graph/retrieval.py` | Shared hybrid profiles, glossary/context steering, and Compass serialization. |
| `src/context_knowledge_graph/repository.py` | Atlas access, evidence records, source verification, and legacy context enrichment. |
| `src/context_knowledge_graph/config.py` | Configuration and local environment loading. |
| `web/src/main.jsx`, `web/src/CapabilityGuide.jsx` | Studio UI, document/relationship inspectors, and capability framing. |
| `web/src/legacy.jsx` | Earlier agent workflow and generated business explanation diagrams. |
| `src/context_knowledge_graph/agents.py`, `workflow.py` | Legacy domain handlers and LangGraph routing. |
| `src/context_knowledge_graph/memory.py` | Optional standalone Agent Engine memory SDK adapter. |
| `src/context_knowledge_graph/scenarios.py` | Human questions and claim references; no expected answers. |
| `scripts/` | Query comparison, fixture maintenance, and evidence smoke checks. |

Keep the full Python package when sharing: the API imports legacy workflow components even if only the Studio is demonstrated. The main Studio endpoints are `/api/explorer/catalog`, `/api/explorer/prepare`, and `/api/explorer/run`.

## Local development

Prerequisites: Python 3.11+, uv, Node compatible with the Vite toolchain, and configured Atlas fixtures. The Docker build uses Python 3.12 and Node 22.

```bash
uv sync
npm ci --prefix web
npm run build --prefix web
uv run uvicorn context_knowledge_graph.api:app --host 127.0.0.1 --port 8000
```

For frontend hot reload, run `npm run dev --prefix web` in another terminal. Vite proxies API requests to port 8000.

## Validation

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
npm run build --prefix web
```

Backend tests use in-memory synthetic fixtures and do not modify Atlas. With Docker serving port 8080, run Studio browser checks from the `web` directory:

```bash
npx playwright test tests/pipeline.spec.js
```

Playwright is configured to use installed Google Chrome. Studio browser checks use real Atlas retrieval, including embeddings and reranking. The legacy hover test intercepts its investigation endpoint with a browser-only fixture. The separate `tests/explorer.spec.js` suite includes a real Atlas/model investigation that can update synthetic context.

The current baseline was checked on October 29, 2026: **42 backend tests and ten Studio browser tests passed**, alongside lint, frontend build, and Docker checks. This includes purpose/date prefiltering, optional ANN, one-aggregation execution, discovery-only query context, preserved teaching results, and latency comparison arithmetic. Six hybrid comparisons preserved the pre-change top-20 result sets and first ten candidates; ANN matched filtered exact top-20 results in all six small-fixture comparisons. These are dated observations, not guarantees about a larger deployment or a vector-only recall benchmark.

A separate read-only evidence smoke check is available:

```bash
uv run python scripts/evaluate_pricing.py
```

It disables model calls and context writes, checks source resolution/evidence status for P01–P16, and writes `data/pricing-smoke-results.json`. It does not score natural-language answer quality. See the [scenario catalog](pricing-scenarios.md) for evaluator checks and repeat-run logging.

## Legacy agents and optional memory

The `/legacy` route has six roles implemented as methods on one `Agents` object, not independently deployed autonomous agents. The Coordinator routes intent; Claim leads resolution; Member resolves identifiers; Drug, Plan, and PA gather independent evidence concurrently. Claim reconciles supported findings and the Coordinator presents them. PA approval alone does not prove a cost-sharing exception.

Each investigation injects evidence requirements from `scenarios.py` before model interpretation. It distinguishes recorded facts from bounded reconstruction, cites sources, and states missing evidence. Source verification and authorized context enrichment remain separate from model commentary. Operational records remain read-only.

To enable legacy interpretation, configure `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, and `LLM_AUTH_HEADER`, then set `CONTEXT_KNOWLEDGE_GRAPH_USE_LLM=true`. To prevent legacy context enrichment, set `CONTEXT_KNOWLEDGE_GRAPH_CONTEXT_WRITES=false`. The Studio itself never calls the answer LLM or writes business collections.

### Standalone memory adapter


The optional `agent-engine-sdk-memory` adapter is isolated in `src/context_knowledge_graph/memory.py`. No Agent Engine agent-runtime SDK is imported.

For existing hosted standalone memory, configure:

```text
AGENTIC_MEMORY_PROJECT_ID=<memory project>
AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN=<short-lived token>
```

`AGENTIC_MEMORY_BASE_URL` optionally overrides the gateway. For a local standalone memory backend, set only its OE proxy URL and leave project/token unset. From Docker Desktop, use `host.docker.internal` for a service on your computer, not `localhost`.

This app does not provision the memory service. Each call binds server-derived client/user/agent/session identity. Agent-specific composite memory-owner IDs add separation even if the memory server filters only by user. Reusable business findings travel through shared domain context. Memory is advisory and never overrides current pricing evidence. The UI reports unconfigured/unavailable memory explicitly. Background extraction and publishing trusted procedural/taxonomic records require separate memory-server configuration. Token rotation is an external responsibility.

Official reference: https://www.mongodb.com/docs/agentengine/add-features/memory-only/

## Persistence and extension points


The application does not configure a workflow checkpointer, SQLite database, or persistent Docker volume. Legacy investigations execute with request-local workflow state. This is a **single-process, single-replica synthetic demo**; capacity coordination, authenticated end-user identity, and per-client authorization remain extension points. Business context in Atlas and optional managed agent memory are separate from workflow checkpointing.

The API uses a fixed synthetic-demo identity without authentication. The Compose port is bound only to your computer. Domain-specific context-write rules and operational read-only access remain enforced by the application.

Cancellation/timeouts do not undo context writes that already completed. Runtime events are request-scoped telemetry, not hidden model reasoning. New session IDs isolate conversational memory; they do not reset shared business context.


## Search performance controls

Shared retrieval uses purpose/date prefilters inside Vector Search with a fixed 50-result branch budget. `vector_mode` selects `exact` (default) or `ann`; `num_candidates` defaults to 1,000 for ANN. The main UI always sends `execution_mode: "preview"` for teaching runs. A separate **Run full pipeline** button sends `execution_mode: "single"` and records the final aggregation latency separately, preserving teaching rows and timings. The comparison uses summed preview query times versus the full aggregation time, supports either timing direction, and resets on query changes. Single-pass API streams mark intermediate stages as included without supplying rows or stage timings; the final event reports one aggregation and total pipeline elapsed time. Existing rerank limits remain 20 hybrid candidates → first 10 reranked → top 3 graph seeds.

Search-index migration and result comparison are explicit CLI operations documented in the [demo guide](demo-guide.md#reproduce-the-retrieval-comparison). They are never triggered by opening the UI. Ordinary rule traversal and entry-point indexes are separate from the Search indexes.
