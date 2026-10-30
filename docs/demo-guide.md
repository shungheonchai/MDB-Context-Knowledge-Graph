# Demo guide

Follow the [setup instructions](../README.md#start-here), then open **http://localhost:8080**. The earlier agent demonstration remains at `/legacy`. Commands and source paths below are relative to the repository root unless stated otherwise.

The main demonstration is about modeling and selecting business context. Its output is a candidate rule/evidence bundle, not a claim-adjudication replay or a newly calculated member payment. Existing source facts, recorded decisions, rule applicability and precedence must still establish the answer.

## Capabilities, procedures, rules, and domains

The opening guide distinguishes business outcomes from data ownership. Select **Compare two copays**, **Investigate OOP maximum**, or **Explain PA impact** to see an illustrative procedure, the rule families it needs, and the contributing data domains. The expandable catalog provides ten planning examples, not ten implemented agents.

A capability can span several domains; the same domain can support many capabilities. Procedural memory can organize the investigation, versioned rules establish applicable conditions and calculations, and domain-context records supply attributed evidence. Neither a capability nor a procedure implies a new agent or collection. The examples do not execute an investigation or alter the pipeline controls below.

## The three evolutions

| Evolution | What executes | What to explain |
|---|---|---|
| 01 — Domain entry points | `$match` then `$graphLookup` | `entryPoint: true`, a selected `ruleDomain`, and the effective date discover every eligible starting rule. Declared links then retrieve cross-domain dependencies. No starting `ruleId` is supplied. |
| 02 — Discover and traverse | `$search` + `$vectorSearch` inside `$rankFusion`, native `$rerank`, then `$graphLookup` | Hybrid retrieval finds candidates; reranking jointly considers query and rule text; graph traversal preserves explicit dependencies regardless of semantic score. |
| 03 — Reuse what you know | Conceptual integration contract only | The coworker demo owns semantic/episodic cache and procedural memory. A valid cache hit can reuse attributed evidence; misses continue through the procedure and retrieval. |

The workbench does not provision memory, simulate cache hits, write business records, or call the answer LLM. Native Voyage embeddings and reranking are real Atlas operations. The legacy agent path retains its existing behavior and optional SDK memory adapter.

## Rehearse evolution 01

1. Keep **Domain entry points** selected and choose **Pricing**. The initial query uses `entryPoint: true`, `ruleDomain: "Pricing"`, and effective dates; it has no `ruleId` condition.
2. Use rule date **2026-10-15** and `maxDepth: 5`. Click **Run pipeline**.
3. Select `$match`: inspect all five applicable Pricing entry-point versions and the explicit date interval. There are six marked Pricing documents across history, representing five business rule IDs; the MAC versions have non-overlapping date intervals.
4. Select `$graphLookup`: inspect the connected versions from every selected entry point. Each result document owns its graph; the visualization merges shared nodes for readability. Open **Relationships**, hover or focus a box to highlight its outgoing links, hover an edge for its relationship type, and select a node to inspect its document below.
5. Change `maxDepth` to 2 and run again to compare a smaller relationship neighborhood. Counts now reflect multiple entry points. Single-root traversal counts do not describe the combined domain graph.
6. Choose **Versioned rule relationships** in the document-model section. Compare the MAC rule's version 2 with version 3. September retains the earlier topology; October 1 introduces the expanded dependencies.
7. Open **Stage pipeline** or use **Copy full Compass pipeline**. The exported syntax uses `ISODate(...)` and `ObjectId(...)`, so it can be pasted into Compass Aggregations / Text mode.

Each selected entry point is depth 0 in its own graph. `maxDepth` is a distance ceiling, not a request for an exact number of documents. Shared dependencies are deduplicated. Dates use an inclusive start and exclusive end. Graph depth and result order do not determine business execution precedence.

## Rehearse evolution 02

Select **Discover and traverse**. Native reranking is on by default; turn it off for the hybrid baseline. The candidate budget is **20 hybrid results → first 10 reranked → top 3 graph seeds**. An explicit `$limit: 10` before `$rerank` and `numDocsToRerank: 10` make that budget visible in Compass.

### Terminology question

> Why am I still paying coinsurance after reaching my OOPM?

Select the OOP maximum scenario and **Terminology + RRF**. The default retrieval date is October 25. The profile expands OOPM separately from related accumulator concepts and boosts rule names/subtypes. Inspect **Query context** to distinguish those expansions from recorded claim facts.

Run the pipeline and inspect hybrid candidates, then reranked seeds and their scores. The UI shows the observed hybrid rank alongside the reranked position. Native `$rerank` uses `rerank-2.5` on `ruleName` and `ruleDataText`. It refines the candidate order and selects up to three seeds. It does not guarantee the same first rule as the non-reranked CLI comparison.

The two example claims record $90 on October 25 and $0 on October 30. Do not accept the question's premise as proof that coinsurance was charged after the limit. Establish timing from accumulator/source evidence; resolve each fill's rule versions independently when explaining both claims.

### General payment question

> Why was I charged $25?

Choose the $25 scenario and **Claim context + RRF**. The selected claim is `demo-claim-prior`, dated September 15, with a recorded $25 copay. Show the contextual facts added to retrieval, and compare with **Balanced RRF**.

The recorded source rule is `generic-rule-v1`. The synthetic ObjectId rule library illustrates retrieval and graph context; it is not evidence that a similarly named rule executed this claim. Dollar amounts in the user's question are not used as applicability filters.

## What the stage inspector shows

- A plain-language explanation of why the stage exists and how it supports context selection.
- Declared input/output, executable cumulative pipeline, actual returned documents, and preview elapsed time.
- Preserved RRF details and scores, native rerank scores, source IDs/versions and relationships.
- **Query context** appears only in evolution 02. It compares all three profiles, shows the actual expanded query and lexical boost clauses, and separates glossary equivalents, related concepts, and recorded claim facts. Evolution 01 keeps its focus on deterministic domain/date selection.
- A graph of the connected rules across Pricing, Plan, Member, Drug and Prior auth.
- Read-only source-shaped operational/context examples and historical MAC rule versions.

**Run pipeline** always executes the individual teaching previews. Each preview runs its cumulative prefix, so the later previews repeat upstream retrieval and reranking. Their displayed times are not exclusive per-stage costs.

A separate **Run full pipeline** button sits to the right of the final `$graphLookup` stage. It executes the complete aggregation once, preserves all teaching results, and shows its total latency in the comparison panel below the stage rail. You can run it before or after the teaching previews.

The panel compares the **sum of individual preview query times** against the **one-aggregation full-run time**. It displays the observed difference in either direction and clears both measurements when query settings change. The full-run result is measured separately; it does not populate intermediate stage rows or overwrite preview timings. A failed or cancelled full run retains completed teaching results. Network, cache, and model variability mean this is a one-run comparison, not a production benchmark.

The copied Compass pipeline always runs as one complete aggregation.

## Context model and limits

Section 01 now includes a selector for **Specialty Drug Dispensing Fee Cap** (`ruleId: 467618533fe0438a98b1dde4`), an isolated example excluded from entry points and curated hybrid strategies. Version 1 runs January 1 to May 1 with mock fee cap 150; version 2 runs May 1 to September 1 with cap 125; version 3 runs from September 1 onward with cap 100. End dates are exclusive, and the previous versions' end dates are closed at the next start date. Section 01 is labeled **Versioned rule content**. Section 02 is labeled **Versioned rule relationships** and shows a compact relationship diagram instead of full rule documents: choose MAC version 2 or 3, inspect direct links, and optionally expand the linked chains. Individual calculations and raw rule fields stay in section 01. The collection now has 3,021 documents, with the same 31 curated strategy versions.

Each rule version is a separate document. Its `ruleData`, `relationships`, `effStartDate`, and `effEndDate` belong to that version; the business `ruleId` stays stable across versions. Both the starting point and every graph hop are filtered to the chosen date. A rule that is not textually similar can still be retrieved through a declared dependency.

Discovery searches curated `purpose: traversal-strategy` documents within the larger mock collection. Other generated examples are excluded consistently, so this is not an all-corpus recall evaluation. `entryPoint` is reported rather than required during discovery, allowing Member concept rules to appear; a production procedure should apply its own execution-routing policy.

The `autoEmbed_ruleData` index includes `purpose`, `effStartDate`, and `effEndDate` as filter fields, alongside its domain/type filters. Both retrieval branches apply the same curated-purpose and effective-date scope inside Search. Vector results are capped at 50 per branch; there is no corpus-sized vector result limit or trailing applicability `$match`.

**Filtered exact** is the default vector baseline. **Filtered ANN** is an explicit comparison mode using `numCandidates: 1000` and `limit: 50`; the API also accepts `num_candidates` from 50 to 10,000. Evaluate ANN against exact results before adopting it at larger volumes. The current curated set is small, so neither an ANN speedup nor production-scale throughput is established. Cross-domain dependencies are retained during graph expansion; no Pricing-only or entry-point-only traversal filter is added.

The runtime never creates or updates Search indexes automatically. For a compatible existing vector index, run `uv run python scripts/configure_vector_index.py` from the runtime directory to inspect the proposed additions, or explicitly add `--apply` to create/update and wait for readiness. Existing embedding settings are preserved. The neutral index assets are in `demo/hybrid-search/`; the lexical index name remains configurable.

## Memory handoff

Evolution 03 makes no requests to a cache or memory service. Its contract includes claim identity, authorization scope, intent, effective date, source/rule versions, freshness, selected rule IDs, source references, missing evidence and outcome. Procedures reference rules and tool requirements; claim-specific facts are injected during execution. A cache miss and a new investigation must not be presented as a memory hit.

## Implementation and verification

- Shared query builders: `context-knowledge-graph-runtime/src/context_knowledge_graph/retrieval.py`.
- Workbench plans, catalog and streaming stage previews: `context-knowledge-graph-runtime/src/context_knowledge_graph/explorer.py`.
- Main UI: `context-knowledge-graph-runtime/web/src/main.jsx`; preserved agent UI: `legacy.jsx`.
- API: `/api/explorer/catalog`, `/api/explorer/prepare`, `/api/explorer/run`.
- Backend tests cover historical filtering, stage order, explicit rerank bypass, BSON query export, conceptual memory validation and safe native-stage failures.
- Browser checks execute real Atlas graph-depth changes, both questions with native reranking, source/version inspection, and the conceptual handoff. Screenshots are stored locally in `context-knowledge-graph-runtime/data/pipeline-workbench-*.png`.

The workbench is the main route; the earlier agent handlers, API and context write behavior remain available through the legacy view.

## CLI comparison and Compass export

The CLI compares the same two questions across `balanced_rrf`, `terminology_rrf`, and `context_rrf`, using equal lexical/vector RRF weights. Profiles differ in glossary expansion, lexical field boosting, and injected claim context. They do not implement Relative Score Fusion or a separate vector-result injection semantic-boosting mechanism. The CLI comparison does not include native reranking; the Studio discovery path adds it.

From `context-knowledge-graph-runtime`:

```bash
uv run python scripts/demo_hybrid_search.py
uv run python scripts/demo_hybrid_search.py --case oopm --profile terminology_rrf
uv run python scripts/demo_hybrid_search.py --case charge25 --profile context_rrf
uv run python scripts/demo_hybrid_search.py --prepare-only
uv run python scripts/demo_hybrid_search.py --vector-mode ann --num-candidates 1000
```

The default comparison issues six real Atlas queries. `--prepare-only` exports queries without issuing search/embedding queries; it still reads Atlas to resolve fixture context. Reports and Compass pipelines go to the ignored `data/hybrid-demo/` directory. Open the configured database's `rulesSets` collection in Compass Aggregations / Text mode and paste the generated `.compass.js` pipeline. Filenames use `<case>-<profile>.compass.js`, for example `oopm-terminology_rrf.compass.js`.

Compare all three profiles on both questions. Inspect `scoreDetails`, expansions, injected claim facts, and connected versions; fusion scores are relevance signals, not probabilities of applicability. Do not promise a particular ranking: results can vary with data, indexes, and retrieval behavior. A rank change on two questions is a demonstration, not an accuracy evaluation.

Both comparison branches restrict candidates to curated traversal-strategy documents and the effective date. Discovery reports entry-point flags rather than requiring them, allowing concept candidates. The comparison script reads business collections and writes reports locally; it does not create Search indexes. The legacy investigation route does not automatically call these profiles.

## Reproduce the retrieval comparison

From the runtime directory, run `uv run python scripts/benchmark_hybrid_search.py`. This executes both questions across three profiles with exact and ANN retrieval: twelve real hybrid queries, with no reranking or graph stages. It records top-20 result overlap/order, eligible-version counts, and observed elapsed times in ignored `data/hybrid-performance-comparison.json`.

An optional `--baseline <path>` compares exact results against a prior JSON report containing `comparisons` with `case`, `profile`, `ids`, and `elapsedMs`. The prefilter migration baseline is a local artifact, not distributed fixture data. Measurements include query embedding, network, and cache effects. Hybrid top-20 overlap is not a vector-only recall score or a production load benchmark.
