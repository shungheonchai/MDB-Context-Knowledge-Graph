# Context Knowledge Graph

A local Context Engineering Studio for exploring how MongoDB documents, hybrid retrieval, reranking, and versioned relationships support pharmacy-pricing explanations. Built with FastAPI and React, packaged as one Docker Compose service.

## Start here

Prerequisites: Docker with Compose, an accessible Atlas deployment containing the compatible synthetic fixtures, and its database credentials. The Studio does not create a new Atlas cluster, import the complete dataset, or provision Search indexes automatically. Use an existing demo deployment or arrange a compatible fixture snapshot before running it.

From the repository root, create the single local configuration file if you do not already have it:

```bash
cp context-knowledge-graph-runtime/.env.example context-knowledge-graph-runtime/.env
```

Edit the ignored runtime `.env` locally:

```dotenv
CONTEXT_KNOWLEDGE_GRAPH_MONGODB_URI=<your MongoDB connection string>
CONTEXT_KNOWLEDGE_GRAPH_DATABASE=context_knowledge_graph_demo
CONTEXT_KNOWLEDGE_GRAPH_LEXICAL_INDEX=context_knowledge_graph_rules_lexical
CONTEXT_KNOWLEDGE_GRAPH_USE_LLM=false
```

Use your deployment's actual database and lexical-index names. It also needs the `autoEmbed_ruleData` vector index and support for the native pipeline stages used by the demo. The [lexical index definition](context-knowledge-graph-runtime/demo/hybrid-search/lexical-index.json) and [vector index definition](context-knowledge-graph-runtime/demo/hybrid-search/vector-index.json) are included. The vector index must include purpose/date filter fields; see the [index setup instructions](docs/demo-guide.md#context-model-and-limits). Main-view retrieval does not require an answer-model API key or memory service. Optional model settings apply to the legacy agent explorer.

```bash
cd context-knowledge-graph-runtime
docker compose up --build -d
```

Open **http://localhost:8080** to launch the Context Engineering Studio.

To stop the demo, run from the same runtime directory:

```bash
docker compose down
```

The app does not persist execution checkpoints. All local settings live in `context-knowledge-graph-runtime/.env`; both Docker and Python use that one file. For non-Docker runs, existing process environment variables take precedence. The `.env` file and generated reports stay out of Git.

## Documentation

| Guide | Purpose |
|---|---|
| [Demo guide](docs/demo-guide.md) | Rehearse the three retrieval evolutions, explain each stage, compare hybrid profiles, and export Compass pipelines. |
| [Data guide](docs/data-guide.md) | Understand domain/context modeling, the dated fixture inventory, rule versions, proposed memory/cache behavior, and fixture maintenance. |
| [Pricing scenarios](docs/pricing-scenarios.md) | Repeat the P01–P16 legacy investigations and evaluate evidence; includes additional fixture storylines. |
| [Development guide](docs/development.md) | Navigate the code, run locally, test changes, and understand the optional legacy agent/memory path. |

## What is implemented

- Domain entry points: `$match → $graphLookup`, with effective-date filtering and no fixed starting rule ID.
- Discovery: prefiltered exact/optional ANN hybrid search → native `$rerank` → `$graphLookup`, with stage explanations, actual results, and copyable queries.
- Individual teaching previews plus a separate full-pipeline button that compares one-aggregation latency against the preview total.
- Document inspection: separate rule versions, versioned relationships, operational source records, and source-shaped shared context.
- Interactive relationship diagrams: hover or focus a box to highlight outgoing connections.
- Business framing: capabilities span data domains; procedures organize investigation; rules and attributed evidence establish applicability.

The memory-assisted third evolution is a conceptual handoff. Main-view operations read business data without writing it or calling the answer LLM. The legacy explorer can enrich shared context when enabled. All fixtures are synthetic; retrieved rules are candidates, not proof of recorded adjudication. This demo uses an application-owned runtime; Agent Engine hosting and Kubernetes are not required.
