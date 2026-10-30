"""Read-only, stage-by-stage Atlas rule retrieval workbench."""

import asyncio
import json
import logging
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .repository import plain
from .retrieval import CASES, PROFILES, make_pipeline, shell

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/explorer")


class ExploreRequest(BaseModel):
    chapter: Literal["known", "discover"] = "known"
    case_id: Literal["oopm", "charge25"] = "charge25"
    question: str = Field(default="Why was I charged $25?", min_length=1, max_length=2000)
    profile: Literal["balanced_rrf", "terminology_rrf", "context_rrf"] = "context_rrf"
    domain: Literal["Pricing", "Plan", "Member", "Drug", "Prior auth"] = "Pricing"
    as_of: str = Field(default="2026-10-15", pattern=r"^\d{4}-\d{2}-\d{2}$")
    max_depth: int = Field(default=5, ge=0, le=7)
    rerank: bool = True
    execution_mode: Literal["preview", "single"] = "preview"
    vector_mode: Literal["exact", "ann"] = "exact"
    num_candidates: int = Field(default=1000, ge=50, le=10000)


def interval(date):
    return {"effStartDate": {"$lte": date}, "effEndDate": {"$gt": date}}


def graph_stages(date, depth):
    return [
        {
            "$graphLookup": {
                "from": "rulesSets",
                "startWith": "$ruleId",
                "connectFromField": "relationships.targetRuleId",
                "connectToField": "ruleId",
                "as": "ruleGraph",
                "maxDepth": depth,
                "depthField": "depth",
                "restrictSearchWithMatch": interval(date),
            }
        },
        {
            "$set": {
                "ruleGraph": {
                    "$sortArray": {"input": "$ruleGraph", "sortBy": {"depth": 1, "ruleName": 1}}
                }
            }
        },
    ]


def describe_stage(key, label, why, input_text, output_text, pipeline, note=""):
    return {
        "id": key,
        "label": label,
        "why": why,
        "input": input_text,
        "output": output_text,
        "pipeline": pipeline,
        "compass": shell(pipeline),
        "note": note,
    }


def build_plan(body, claims, count):
    try:
        date = datetime.fromisoformat(body.as_of).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("Choose a valid rule effective date") from exc
    case = next(c for c in CASES if c["id"] == body.case_id) | {"question": body.question}
    stages, config = [], {}
    if body.chapter == "known":
        pipeline = [
            {"$match": {"ruleDomain": body.domain, "entryPoint": True, **interval(date)}},
            {"$sort": {"ruleName": 1, "version": -1, "_id": 1}},
        ]
        stages.append(
            describe_stage(
                "match",
                "$match",
                "Discover all designated entry points for the selected domain and effective date. No rule ID is supplied. This deterministic domain filter does not interpret the question; hybrid retrieval adds question-specific selection in the next evolution.",
                "Selected rule domain + entryPoint flag + effective date",
                "All applicable domain entry-point versions",
                deepcopy(pipeline),
            )
        )
    else:
        contextual_claims = deepcopy(claims)
        for claim in contextual_claims:
            claim["serviceDate"] = date
        prepared, config = make_pipeline(
            case,
            contextual_claims,
            body.profile,
            count,
            vector_mode=body.vector_mode,
            num_candidates=body.num_candidates,
        )
        pipeline = [
            prepared[0],
            {"$limit": 20},
            {
                "$set": {
                    "fusionDetails": {"$meta": "scoreDetails"},
                    "fusionScore": {"$meta": "score"},
                }
            },
        ]
        stages.append(
            describe_stage(
                "hybrid",
                "Hybrid search",
                "Combine precise terminology and semantic meaning. The selected profile controls glossary expansion and field boosts; reciprocal rank fusion combines both rankings at equal weights.",
                "Question + optional recorded claim context",
                "Up to 20 candidate rules and lexical/vector contributions",
                deepcopy(pipeline),
                "Both retrieval branches prefilter purpose and effective dates. Filtered exact vector search is the baseline; ANN is an optional recall/latency comparison, not an accuracy guarantee.",
            )
        )
        if body.rerank:
            pipeline += [
                {"$limit": 10},
                {
                    "$rerank": {
                        "query": {"text": config["retrievalText"]},
                        "path": ["ruleName", "ruleDataText"],
                        "numDocsToRerank": 10,
                        "model": "rerank-2.5",
                    }
                },
                {"$set": {"rerankScore": {"$meta": "score"}}},
                {"$limit": 3},
            ]
            stages.append(
                describe_stage(
                    "rerank",
                    "$rerank",
                    "Rerank the first ten hybrid candidates against the question, preserve the fusion score, then retain the top three seeds. Neither score establishes that a rule applied to the claim.",
                    "First 10 of the up to 20 hybrid candidates",
                    "Up to 3 reranked seeds + before/after scores",
                    deepcopy(pipeline),
                )
            )
        else:
            pipeline += [{"$limit": 3}]
    pipeline += graph_stages(date, body.max_depth)
    stages.append(
        describe_stage(
            "graph",
            "$graphLookup",
            "Follow explicit, versioned relationships to collect dependencies whose wording may never match the question. Keep cross-domain evidence and relationship types. Depth is distance, not execution priority.",
            "Selected seeds + relationships.targetRuleId",
            "Rule documents connected by declared relationships",
            deepcopy(pipeline),
            "Candidate seeds are not required to have entryPoint=true in discovery mode, so Member concepts remain discoverable. Apply an execution-routing policy separately."
            if body.chapter == "discover"
            else "The seed is depth 0. After every reachable node is found, increasing maxDepth does not add nodes.",
        )
    )
    facts = [
        {
            "claimId": c["_id"],
            "serviceDate": plain(c.get("serviceDate")),
            "memberPaidCents": c.get("adjudication", {}).get("memberPaidCents"),
            "components": c.get("adjudication", {}).get("components", {}),
            "recordedRuleId": c.get("adjudication", {}).get("ruleId"),
            "planRef": c.get("planRef"),
        }
        for c in claims
    ]
    return {
        "chapter": body.chapter,
        "question": body.question,
        "asOf": date.isoformat(),
        "profile": body.profile,
        "stages": stages,
        "pipeline": pipeline,
        "compass": shell(pipeline),
        "queryConfig": config,
        "claimFacts": facts,
        "candidateScope": "Curated traversal-strategy documents; effective-dated versions; no evaluator data",
        "executionMode": body.execution_mode,
        "executionNote": (
            "Single-pass execution runs the full aggregation once. Only final results are materialized; earlier stages remain inspectable definitions. Elapsed time covers the whole pipeline, not graph-only time."
            if body.execution_mode == "single"
            else "Each stage preview executes its cumulative pipeline prefix independently. Preview times include repeated upstream work and are not additive stage timings."
        ),
    }


def catalog(repo):
    collection = repo.db.rulesSets
    total = collection.count_documents({})
    curated = collection.count_documents({"purpose": "traversal-strategy"})
    entry = list(
        collection.find(
            {"entryPoint": True},
            {
                "ruleId": 1,
                "ruleName": 1,
                "ruleDomain": 1,
                "version": 1,
                "effStartDate": 1,
                "effEndDate": 1,
            },
        ).sort("ruleName", 1)
    )
    rule_versions = list(
        collection.find({"ruleId": ObjectId("467618533fe0438a98b1dde4")}).sort("version", 1)
    )
    rule_example = rule_versions[0] if rule_versions else None
    mac = list(collection.find({"ruleId": ObjectId("467618533fe0438a98b1dde8")}).sort("version", 1))
    relationship_versions = []
    for version in mac:
        graph = list(
            collection.aggregate(
                [
                    {"$match": {"_id": version["_id"]}},
                    *graph_stages(version["effStartDate"], 5),
                    {
                        "$project": {
                            "ruleGraph.ruleId": 1,
                            "ruleGraph.ruleName": 1,
                            "ruleGraph.ruleDomain": 1,
                            "ruleGraph.version": 1,
                            "ruleGraph.relationships": 1,
                            "ruleGraph.depth": 1,
                        }
                    },
                ],
                maxTimeMS=15000,
            )
        )
        relationship_versions.append(
            {
                "version": version["version"],
                "effStartDate": version["effStartDate"],
                "effEndDate": version["effEndDate"],
                "ruleId": version["ruleId"],
                "ruleName": version["ruleName"],
                "directLinks": len(version.get("relationships", [])),
                "nodes": graph[0]["ruleGraph"] if graph else [],
            }
        )
    indexes = [
        {
            "name": i["name"],
            "type": i.get("type"),
            "status": i.get("status"),
            "queryable": i.get("queryable", False),
        }
        for i in collection.list_search_indexes()
    ]
    operational = repo.db.claims.find_one({"_id": "demo-claim-prior", "provenance.synthetic": True})
    context = repo.db.claims_context.find_one({"_id": "demo-claim-prior"})
    return plain(
        {
            "database": repo.db.name,
            "collection": "rulesSets",
            "totalRules": total,
            "curatedRules": curated,
            "entryPoints": entry,
            "sampleRule": rule_example,
            "ruleVersionExamples": rule_versions,
            "versionExamples": relationship_versions,
            "indexes": indexes,
            "cases": CASES,
            "profiles": PROFILES,
            "rawExample": operational,
            "contextExample": context,
            "memoryHandoff": {
                "status": "conceptual",
                "owner": "Coworker's memory demo",
                "steps": [
                    "Semantic / episodic cache",
                    "Procedural memory",
                    "Hybrid search",
                    "$rerank",
                    "$graphLookup",
                ],
                "contract": [
                    "Cache key includes claim identity, authorization scope, effective date, question intent, and source/rule versions.",
                    "A cache hit reuses attributed evidence only when applicable and fresh; a miss continues to the investigation procedure.",
                    "Procedural memory supplies an approved procedure and rule references. It does not change rule authority or replace claim-specific facts.",
                    "Carry selected rule IDs/versions, source references, missing evidence, and outcome back to the memory demo.",
                ],
            },
        }
    )


async def prepare(repo, body):
    case = next(c for c in CASES if c["id"] == body.case_id)
    claims = await asyncio.to_thread(
        lambda: [
            repo.db.claims.find_one({"_id": key, "provenance.synthetic": True})
            for key in case["claim_ids"]
        ]
    )
    if not all(claims):
        raise ValueError("Selected synthetic demo claims are unavailable")
    count = await asyncio.to_thread(repo.db.rulesSets.count_documents, {})
    return build_plan(body, claims, count)


@router.get("/catalog")
async def get_catalog(request: Request):
    try:
        return await asyncio.to_thread(catalog, request.app.state.repo)
    except Exception as exc:
        log.warning("Explorer catalog: %s", type(exc).__name__)
        raise HTTPException(
            503, "Atlas rule catalog is unavailable. Check the connection."
        ) from None


@router.post("/prepare")
async def get_plan(body: ExploreRequest, request: Request):
    try:
        return plain(await prepare(request.app.state.repo, body))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/run")
async def run_plan(body: ExploreRequest, request: Request):
    if request.app.state.capacity.locked():
        raise HTTPException(429, "Another set of demonstrations is running. Retry shortly.")
    try:
        plan = await prepare(request.app.state.repo, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    async def stream():
        async with request.app.state.capacity:
            yield json.dumps({"kind": "plan", "plan": plain(plan)}) + "\n"
            results = []
            run_started = time.perf_counter()
            single = body.execution_mode == "single"
            if single:
                for stage in plan["stages"][:-1]:
                    yield (
                        json.dumps({"kind": "stage", "id": stage["id"], "status": "included"})
                        + "\n"
                    )
            execution_stages = plan["stages"][-1:] if single else plan["stages"]
            for stage in execution_stages:
                yield json.dumps({"kind": "stage", "id": stage["id"], "status": "running"}) + "\n"
                started = time.perf_counter()
                try:
                    rows = await asyncio.to_thread(
                        lambda: list(
                            request.app.state.repo.db.rulesSets.aggregate(
                                stage["pipeline"], maxTimeMS=45000
                            )
                        )
                    )
                    if stage["id"] == "match" or (single and body.chapter == "known"):
                        rule_ids = [str(row["ruleId"]) for row in rows]
                        if len(rule_ids) != len(set(rule_ids)):
                            raise ValueError("Overlapping effective entry-point versions")
                    nodes = {str(n["_id"]) for row in rows for n in row.get("ruleGraph", [])}
                    event = {
                        "kind": "stage",
                        "id": stage["id"],
                        "status": "completed",
                        "rows": plain(rows),
                        "count": len(rows),
                        "graphNodes": len(nodes),
                        "elapsedMs": round((time.perf_counter() - started) * 1000),
                        "timingScope": "full-pipeline" if single else "cumulative-prefix",
                    }
                    results.append(event)
                    yield json.dumps(event) + "\n"
                except Exception as exc:
                    log.warning("Explorer stage %s: %s", stage["id"], type(exc).__name__)
                    message = (
                        "Native reranking failed. Check Atlas Native Reranking settings or turn off reranking to compare the hybrid baseline."
                        if stage["id"] == "rerank"
                        else "Atlas could not execute the pipeline. Check Search index readiness, native reranking settings, and server logs."
                    )
                    if isinstance(exc, ValueError):
                        message = str(exc)
                    yield (
                        json.dumps(
                            {
                                "kind": "stage",
                                "id": stage["id"],
                                "status": "failed",
                                "message": message,
                            }
                        )
                        + "\n"
                    )
                    return
            final = results[-1]
            yield (
                json.dumps(
                    {
                        "kind": "complete",
                        "summary": f"Retrieved {final['count']} seed document(s) and {final['graphNodes']} unique connected rule versions. These are candidate evidence, not a replay of adjudication. "
                        + (
                            "One full aggregation; no separate intermediate previews."
                            if single
                            else "Independent cumulative previews; upstream stages execute repeatedly."
                        ),
                        "aggregationCalls": len(execution_stages),
                        "elapsedMs": round((time.perf_counter() - run_started) * 1000),
                    }
                )
                + "\n"
            )

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"}
    )
