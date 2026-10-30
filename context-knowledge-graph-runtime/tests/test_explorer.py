from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import OperationFailure

from context_knowledge_graph.api import create_app
from context_knowledge_graph.explorer import ExploreRequest, build_plan
from context_knowledge_graph.memory import OptionalMemory
from context_knowledge_graph.repository import plain


def claims(repo):
    return [repo.db.claims.find_one({"_id": "demo-claim-prior"})]


def test_rule_versions_are_filtered_at_seed_and_every_graph_hop(repo):
    plan = build_plan(ExploreRequest(as_of="2026-09-15", max_depth=7), claims(repo), 3019)
    seed = plan["pipeline"][0]["$match"]
    graph = next(stage["$graphLookup"] for stage in plan["pipeline"] if "$graphLookup" in stage)
    assert seed["effStartDate"]["$lte"] == datetime(2026, 9, 15, tzinfo=UTC)
    assert seed["ruleDomain"] == "Pricing" and seed["entryPoint"] is True
    assert "ruleId" not in seed
    assert not any("$limit" in stage for stage in plan["stages"][0]["pipeline"])
    assert graph["restrictSearchWithMatch"]["effEndDate"] == seed["effEndDate"]
    assert graph["maxDepth"] == 7 and graph["startWith"] == "$ruleId"
    assert "entryPoint" not in graph["restrictSearchWithMatch"]
    assert "ruleDomain" not in graph["restrictSearchWithMatch"]
    assert "ISODate(" in plan["compass"] and '"$date"' not in plan["compass"]


def test_domain_entry_points_do_not_pretend_to_interpret_question(repo):
    first = build_plan(ExploreRequest(question="Why did I pay $25?"), claims(repo), 3019)
    second = build_plan(
        ExploreRequest(question="A completely different question"), claims(repo), 3019
    )
    assert first["pipeline"] == second["pipeline"]
    assert "does not interpret" in first["stages"][0]["why"]


def test_reranking_preserves_fusion_evidence_and_never_prunes_graph_dependencies(repo):
    source = claims(repo)
    before = deepcopy(source)
    request = ExploreRequest(
        chapter="discover",
        case_id="oopm",
        question="Coinsurance after OOPM?",
        profile="terminology_rrf",
    )
    plan = build_plan(request, source, 3019)
    keys = [next(iter(stage)) for stage in plan["pipeline"]]
    assert keys.index("$rankFusion") < keys.index("$rerank") < keys.index("$graphLookup")
    assert [stage["$limit"] for stage in plan["pipeline"] if "$limit" in stage] == [20, 10, 3]
    rerank = next(stage["$rerank"] for stage in plan["pipeline"] if "$rerank" in stage)
    assert rerank["numDocsToRerank"] == 10
    assert any(stage.get("$set", {}).get("fusionDetails") for stage in plan["pipeline"])
    assert plan["queryConfig"]["equivalentExpansions"]
    assert "family out-of-pocket accumulator" not in plan["queryConfig"]["equivalentExpansions"]
    graph = next(stage["$graphLookup"] for stage in plan["pipeline"] if "$graphLookup" in stage)
    assert set(graph["restrictSearchWithMatch"]) == {"effStartDate", "effEndDate"}
    assert source == before
    assert len(plan["stages"]) == 3


def test_baseline_skips_reranking_explicitly(repo):
    plan = build_plan(ExploreRequest(chapter="discover", rerank=False), claims(repo), 3019)
    assert [stage["id"] for stage in plan["stages"]] == ["hybrid", "graph"]
    assert not any("$rerank" in stage for stage in plan["pipeline"])


def test_conceptual_memory_path_cannot_execute_and_inputs_are_bounded():
    for payload in [{"chapter": "memory"}, {"max_depth": 100}, {"domain": "{$ne:null}"}]:
        with pytest.raises(ValidationError):
            ExploreRequest(**payload)
    with pytest.raises(ValueError, match="valid rule effective date"):
        build_plan(ExploreRequest(as_of="2026-99-99"), [], 3019)


def test_failed_native_stage_is_visible_without_leaking_exception(repo, settings, monkeypatch):
    async def fake_prepare(*args):
        return {"stages": [{"id": "rerank", "pipeline": []}], "claimFacts": []}

    def fail(*args, **kwargs):
        raise OperationFailure("SECRET_PROVIDER_DETAIL")

    monkeypatch.setattr("context_knowledge_graph.explorer.prepare", fake_prepare)
    monkeypatch.setattr(type(repo.db.rulesSets), "aggregate", fail)
    with TestClient(create_app(settings, repo, OptionalMemory(settings))) as client:
        response = client.post("/api/explorer/run", json={"chapter": "discover"})
        assert response.status_code == 200
        assert '"status": "failed"' in response.text
        assert "Native reranking failed" in response.text
        assert "SECRET_PROVIDER_DETAIL" not in response.text
        assert '"kind": "complete"' not in response.text


def test_vector_prefilter_replaces_full_corpus_materialization(repo):
    plan = build_plan(ExploreRequest(chapter="discover"), claims(repo), 10_000_000)
    branches = plan["pipeline"][0]["$rankFusion"]["input"]["pipelines"]
    vector = branches["vector"]
    assert len(vector) == 1
    query = vector[0]["$vectorSearch"]
    assert query["exact"] is True
    assert query["limit"] == 50
    assert query["filter"] == {
        "purpose": "traversal-strategy",
        "effStartDate": {"$lte": datetime(2026, 10, 15, tzinfo=UTC)},
        "effEndDate": {"$gt": datetime(2026, 10, 15, tzinfo=UTC)},
    }
    lexical = branches["lexical"][0]["$search"]["compound"]["filter"]
    assert lexical[1]["range"]["lte"] == query["filter"]["effStartDate"]["$lte"]
    assert lexical[2]["range"]["gt"] == query["filter"]["effEndDate"]["$gt"]
    assert "ruleDomain" not in query["filter"]
    assert "entryPoint" not in query["filter"]


def test_ann_is_explicit_and_preserves_scope_and_candidate_budget(repo):
    plan = build_plan(
        ExploreRequest(chapter="discover", vector_mode="ann", num_candidates=1000),
        claims(repo),
        3021,
    )
    query = plan["pipeline"][0]["$rankFusion"]["input"]["pipelines"]["vector"][0]["$vectorSearch"]
    assert "exact" not in query
    assert query["numCandidates"] == 1000
    assert query["limit"] == 50
    assert query["filter"]["purpose"] == "traversal-strategy"
    assert plan["queryConfig"]["vectorMode"] == "ann"
    for payload in [
        {"vector_mode": "unknown"},
        {"num_candidates": 49},
        {"num_candidates": 10001},
        {"execution_mode": "cached"},
    ]:
        with pytest.raises(ValidationError):
            ExploreRequest(**payload)


@pytest.mark.parametrize("mode,calls", [("preview", 3), ("single", 1)])
def test_single_pass_runs_one_aggregation_without_fake_intermediate_results(
    repo, settings, monkeypatch, mode, calls
):
    import json

    executed = []
    source = claims(repo)

    async def fake_prepare(repo, body):
        return build_plan(body, source, 3021)

    def aggregate(self, pipeline, **kwargs):
        executed.append(pipeline)
        return [{"_id": "version-a", "ruleId": "rule-a", "ruleGraph": [{"_id": "dependency-a"}]}]

    monkeypatch.setattr("context_knowledge_graph.explorer.prepare", fake_prepare)
    monkeypatch.setattr(type(repo.db.rulesSets), "aggregate", aggregate)
    with TestClient(create_app(settings, repo, OptionalMemory(settings))) as client:
        response = client.post(
            "/api/explorer/run", json={"chapter": "discover", "execution_mode": mode}
        )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert len(executed) == calls
    assert plain(executed[-1]) == events[0]["plan"]["pipeline"]
    complete = next(event for event in events if event["kind"] == "complete")
    assert complete["aggregationCalls"] == calls
    assert complete["elapsedMs"] >= 0
    if mode == "single":
        included = [event for event in events if event.get("status") == "included"]
        assert [event["id"] for event in included] == ["hybrid", "rerank"]
        assert all("rows" not in event for event in included)
        completed = [event for event in events if event.get("status") == "completed"]
        assert len(completed) == 1 and completed[0]["id"] == "graph"
        assert completed[0]["timingScope"] == "full-pipeline"


def test_query_context_reports_actual_lexical_boosts_separately_from_fusion_weights(repo):
    source = claims(repo)
    source[0].setdefault("adjudication", {})["components"] = {"copayCents": 2500}
    for profile in ["balanced_rrf", "terminology_rrf", "context_rrf"]:
        plan = build_plan(
            ExploreRequest(chapter="discover", question="Coinsurance after OOPM?", profile=profile),
            source,
            3021,
        )
        config = plan["queryConfig"]
        assert config["lexicalVectorWeights"] == {"lexical": 1, "vector": 1}
        if profile == "balanced_rrf":
            assert config["lexicalBoosts"] == []
            assert config["retrievalText"] == "Coinsurance after OOPM?"
        elif profile == "terminology_rrf":
            assert config["lexicalBoosts"][0]["boost"] == 4
            assert config["lexicalBoosts"][0]["paths"] == ["ruleName", "ruleSubType"]
            assert any(
                b["boost"] == 3 and b["operator"] == "phrase" for b in config["lexicalBoosts"]
            )
            assert "out-of-pocket maximum" in config["retrievalText"]
            assert "family out-of-pocket accumulator" not in config["retrievalText"]
        else:
            assert config["lexicalBoosts"] == [
                {
                    "operator": "text",
                    "query": "copay",
                    "paths": ["ruleName", "ruleSubType"],
                    "boost": 4,
                }
            ]
            assert config["claimContext"] in config["retrievalText"]
