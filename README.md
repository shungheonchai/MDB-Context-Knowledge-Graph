# Context Knowledge Graph

A local Context Engineering Studio that demonstrates MongoDB document modeling, hybrid search, reranking, and versioned rule relationships using synthetic pharmacy-pricing data.

## Before you start

You need:

- Docker running with Docker Compose available—for example, through Docker Desktop.
- Access to an Atlas database containing the compatible demo data and ready Search indexes.
- A MongoDB connection string with permission to read that data, and network access to the Atlas deployment.

The app does not load the complete dataset or provision Atlas automatically. For the quickest setup, connect to an existing demo deployment. An empty database will not run the demonstration; index definitions alone do not supply the sample data.

You do not need a separate Python or Node installation, an answer-LLM API key, or a memory service to launch the Studio with Docker.

## Launch the Studio

### 1. Create the configuration file

From the repository root:

```bash
cd context-knowledge-graph-runtime
cp .env.example .env
```

### 2. Fill in your Atlas settings

Open `.env` and set these three values:

```dotenv
CONTEXT_KNOWLEDGE_GRAPH_MONGODB_URI=<your connection string>
CONTEXT_KNOWLEDGE_GRAPH_DATABASE=<existing database name>
CONTEXT_KNOWLEDGE_GRAPH_LEXICAL_INDEX=<existing lexical search index name>
```

Use the actual names supplied with your demo database access. The database and lexical-index names in `.env.example` are examples; they do not create or rename anything in Atlas.

Leave the other template defaults unchanged for Studio-only use: `CONTEXT_KNOWLEDGE_GRAPH_USE_LLM=false`, `CONTEXT_KNOWLEDGE_GRAPH_CONTEXT_WRITES=false`, and the optional LLM/memory credentials blank.

The demo also expects a Vector Search index named `autoEmbed_ruleData`, including purpose and effective-date filters, and support for native hybrid search, automated embeddings, and `$rerank`. If you need to configure the indexes, use the [index setup notes](docs/demo-guide.md#context-model-and-limits), [lexical definition](context-knowledge-graph-runtime/demo/hybrid-search/lexical-index.json), and [vector definition](context-knowledge-graph-runtime/demo/hybrid-search/vector-index.json).

### 3. Start the app

```bash
docker compose up --build -d
```

The first build downloads dependencies and can take a few minutes. Once the app has started, open **http://localhost:8080**.

## Stop the app

From `context-knowledge-graph-runtime`:

```bash
docker compose down
```

## Explore the demo

- **01 — Domain entry points:** select effective-dated starting rules with `$match`, then follow declared dependencies with `$graphLookup`.
- **02 — Discover and traverse:** combine lexical and semantic retrieval, rerank candidates, and expand their relationships. Query context explains the differences between retrieval profiles.
- **03 — Reuse what you know:** a conceptual memory-integration walkthrough; it does not call a memory service.

**Run pipeline** shows individual stage previews. **Run full pipeline**, to the right of the last stage, executes one complete aggregation and compares its latency with the preview total. Hover or focus a graph box to highlight its outgoing connections.

The Studio reads business data without modifying it. Retrieved rules are candidate evidence, not proof that they determined a recorded claim payment.

## Documentation

| Guide | Purpose |
|---|---|
| [Demo guide](docs/demo-guide.md) | Rehearsal, retrieval profiles, index setup, and Compass pipelines. |
| [Data guide](docs/data-guide.md) | Document models, fixture inventory, and maintenance scripts. |
| [Pricing scenarios](docs/pricing-scenarios.md) | Repeatable questions and evaluator checks for the optional legacy agent demo. |
| [Development guide](docs/development.md) | Code structure, local development, testing, and optional legacy agents/memory. |
