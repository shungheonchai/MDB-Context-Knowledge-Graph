import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from context_knowledge_graph.api import create_app
from context_knowledge_graph.events import Execution
from context_knowledge_graph.memory import OptionalMemory
from context_knowledge_graph.models import Finding, Principal
from context_knowledge_graph.repository import digest
from context_knowledge_graph.workflow import build_workflow


def execution():
    return Execution(
        "run-1", "session-1", Principal(user_id="test-user", client_id="synthetic-demo")
    )


async def investigate(repo, settings, ids):
    ex = execution()
    result = await build_workflow(repo, OptionalMemory(settings), ex).ainvoke(
        {"question": "Explain " + ids}
    )
    return result, ex


async def test_recorded_comparison_preserves_operational(repo, settings):
    before = digest(list(repo.db.claims.find()))
    result, ex = await investigate(repo, settings, "demo-claim-current and demo-claim-prior")
    assert [f["status"] for f in result["findings"]] == ["recorded", "recorded"]
    assert "$50.00" in result["answer"]
    assert digest(list(repo.db.claims.find())) == before
    assert any(
        e["kind"] == "context_read" and e["agent"] == "plan" and e["domain"] == "member"
        for e in ex.events
    )
    assert any(
        e["kind"] == "context_relationship" and e["target_domain"] == "drug" for e in ex.events
    )


@pytest.mark.parametrize(
    "suffix", ["missing-drug", "missing-plan", "missing-member", "missing-all-refs"]
)
async def test_missing_references_resolve_without_claim_repair(repo, settings, suffix):
    claim_id = "demo-claim-" + suffix
    before = deepcopy(repo.db.claims.find_one({"_id": claim_id}))
    result, _ = await investigate(repo, settings, claim_id)
    finding = result["findings"][0]
    assert finding["status"] == "reconstructed"
    assert finding["details"]["member_paid_cents"] == 7500
    ctx = repo.db.claims_context.find_one({"claimRef": claim_id})
    assert ctx["resolvedRelationships"]["plan"]["ref"] == "plan-2"
    assert before == repo.db.claims.find_one({"_id": claim_id})


async def test_unknown_identity_does_not_invent_links(repo, settings):
    result, _ = await investigate(repo, settings, "demo-claim-unresolved-identity")
    assert result["findings"][0]["status"] == "insufficient"
    ctx = repo.db.claims_context.find_one({"claimRef": "demo-claim-unresolved-identity"})
    assert not ctx.get("resolvedRelationships")
    assert result["findings"][0]["details"]["pa_status"] == "unknown"


async def test_pa_does_not_imply_discount(repo, settings):
    result, _ = await investigate(repo, settings, "demo-claim-pa")
    assert result["findings"][0]["details"]["pa_changes_cost_sharing"] is False
    assert "without changing cost-sharing" in result["answer"]


async def test_repeat_is_reuse_not_corroboration(repo, settings):
    await investigate(repo, settings, "demo-claim-current")
    _, ex = await investigate(repo, settings, "demo-claim-current")
    assert any(e["kind"] == "context_reinforcement" and e["status"] == "reused" for e in ex.events)
    assert not any(
        e["kind"] == "context_reinforcement" and e["status"] == "corroborated" for e in ex.events
    )


async def test_conflicting_source_does_not_prove_price(repo, settings):
    result, _ = await investigate(repo, settings, "demo-claim-conflict")
    assert result["findings"][0]["status"] == "insufficient"
    assert result["findings"][0]["details"]["conflicts"]


async def test_historical_plan_resolution(repo, settings):
    repo.db.claims.update_one(
        {"_id": "demo-claim-missing-plan"},
        {
            "$set": {
                "serviceDate": repo.db.claims.find_one({"_id": "demo-claim-prior"})["serviceDate"],
                "adjudication.memberPaidCents": 2500,
                "adjudication.components.copayCents": 2500,
            }
        },
    )
    result, _ = await investigate(repo, settings, "demo-claim-missing-plan")
    assert result["findings"][0]["details"]["plan_ref"] == "plan-1"


async def test_cross_domain_write_denied(repo):
    with pytest.raises(PermissionError):
        await repo.write(
            execution(),
            "drug",
            "claim",
            "demo-claim-current",
            Finding(claim_id="x", domain="claim", status="insufficient", summary="x"),
        )


async def test_context_metadata_preserved(repo, settings):
    repo.db.claims_context.insert_one(
        {
            "_id": "demo-claim-current",
            "claimRef": "demo-claim-current",
            "revision": 1,
            "metadata": {"humanNote": {"statement": "Keep this note"}},
            "investigation": {"recordedSourceEvidence": []},
        }
    )
    await investigate(repo, settings, "demo-claim-current")
    assert (
        repo.db.claims_context.find_one({"claimRef": "demo-claim-current"})["metadata"][
            "humanNote"
        ]["statement"]
        == "Keep this note"
    )


def test_api_stream_without_persistent_checkpoints(settings, repo):
    app = create_app(settings=settings, repository=repo)
    with TestClient(app) as client:
        assert not hasattr(app.state, "checkpointer")
        assert "checkpoint" not in client.get("/api/config").json()
        result = client.post(
            "/api/investigate/stream", json={"question": "Explain demo-claim-current"}
        )
        assert result.status_code == 200
        events = [json.loads(line) for line in result.text.splitlines()]
        assert events[-1]["status"] == "completed"
        assert any(e["kind"] == "answer" for e in events)
        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        assert client.get("/api/claims").status_code == 200


def test_local_docker_demo_requires_no_token(settings, repo):
    app = create_app(settings=settings, repository=repo)
    with TestClient(app, client=("172.18.0.1", 50000)) as client:
        assert client.get("/api/config").status_code == 200
        assert client.get("/api/claims").status_code == 200


async def test_unit_price_exception_reconstruction(repo, settings):
    repo.db.plans.update_one(
        {"_id": "plan-2"},
        {
            "$set": {
                "benefit": {
                    "exceptions": [
                        {
                            "exceptionId": "unit-exception",
                            "drugRef": "drug-1",
                            "type": "unit-price",
                            "unitPriceCents": 250,
                        }
                    ]
                }
            }
        },
    )
    repo.db.claims.update_one(
        {"_id": "demo-claim-missing-drug"},
        {
            "$set": {
                "adjudication.allowedAmountCents": 7500,
                "adjudication.components": {"deductibleCents": 7500},
            }
        },
    )
    result, _ = await investigate(repo, settings, "demo-claim-missing-drug")
    assert result["findings"][0]["status"] == "reconstructed"
    assert "$2.50 per unit × 30 units = $75.00" in result["answer"]


async def test_flat_exception_reconstruction(repo, settings):
    repo.db.plans.update_one(
        {"_id": "plan-2"},
        {
            "$set": {
                "benefit": {
                    "exceptions": [
                        {
                            "exceptionId": "flat-exception",
                            "drugRef": "drug-1",
                            "type": "flat-copay",
                            "copayCents": 7500,
                        }
                    ]
                }
            }
        },
    )
    result, _ = await investigate(repo, settings, "demo-claim-missing-plan")
    assert result["findings"][0]["status"] == "reconstructed"
    assert result["findings"][0]["details"]["rule_id"] == "flat-exception"


async def test_stale_resolved_links_removed_when_identity_becomes_unknown(repo, settings):
    await investigate(repo, settings, "demo-claim-missing-all-refs")
    repo.db.claims.update_one(
        {"_id": "demo-claim-missing-all-refs"},
        {"$unset": {"submittedMember": "", "submittedDrug": ""}},
    )
    result, _ = await investigate(repo, settings, "demo-claim-missing-all-refs")
    assert result["findings"][0]["status"] == "insufficient"
    context = repo.db.claims_context.find_one({"claimRef": "demo-claim-missing-all-refs"})
    assert not context["resolvedRelationships"]
    assert context["investigation"]["revisions"]


async def test_minimum_coinsurance_is_explained(repo, settings):
    repo.db.plans.update_one(
        {"_id": "plan-2"},
        {
            "$set": {
                "benefit.defaultCostShare": {
                    "model": "deductible-then-coinsurance",
                    "coinsuranceBps": 2000,
                    "coinsuranceMinCents": 500,
                    "coinsuranceMaxCents": 10000,
                }
            }
        },
    )
    repo.db.claims.update_one(
        {"_id": "demo-claim-current"},
        {
            "$set": {
                "adjudication.memberPaidCents": 500,
                "adjudication.allowedAmountCents": 2000,
                "adjudication.components": {"coinsuranceCents": 500},
            }
        },
    )
    repo.db.client.context_knowledge_graph_archive.decision_traces.update_one(
        {"_id": "trace-demo-claim-current"},
        {
            "$set": {
                "events": [
                    {
                        "type": "rule-applied",
                        "ruleType": "deductible-then-coinsurance",
                        "memberCostCents": 500,
                        "accumulatorsBefore": {
                            "deductibleRemainingCents": 0,
                            "oopRemainingCents": 50000,
                        },
                        "accumulatorsAfter": {
                            "deductibleRemainingCents": 0,
                            "oopRemainingCents": 49500,
                        },
                    }
                ]
            }
        },
    )
    result, _ = await investigate(repo, settings, "demo-claim-current")
    assert "20.00% of $20.00 = $4.00" in result["answer"]
    assert "Minimum: $5.00" in result["answer"]
    assert "$500.00 before → $495.00 after" in result["answer"]


async def test_concurrent_first_context_writes_preserve_both_findings(repo):
    from context_knowledge_graph.models import Finding

    a = Finding(claim_id="claim-a", domain="member", status="recorded", summary="First finding")
    b = Finding(claim_id="claim-b", domain="member", status="recorded", summary="Second finding")
    await asyncio.gather(
        repo.write(execution(), "member", "member", "member-1", a),
        repo.write(execution(), "member", "member", "member-1", b),
    )
    findings = repo.db.members_context.find_one({"memberRef": "member-1"})["investigation"][
        "findings"
    ]
    assert {f["claim_id"] for f in findings} == {"claim-a", "claim-b"}


async def test_changed_source_rejects_stale_context_write(repo):
    ex = execution()
    item = await repo.read(ex, "claim", "claim", "demo-claim-current")
    repo.db.claims.update_one(
        {"_id": "demo-claim-current"}, {"$set": {"adjudication.memberPaidCents": 1}}
    )
    finding = Finding(
        claim_id="demo-claim-current",
        domain="claim",
        status="recorded",
        summary="Stale finding",
        evidence_ids=[item["evidence"].id],
    )
    with pytest.raises(RuntimeError, match="Source changed"):
        await repo.write(ex, "claim", "claim", "demo-claim-current", finding)
    assert repo.db.claims_context.count_documents({}) == 0


def test_memory_identity_is_agent_specific(settings):
    class FakeMemory:
        def bind(self, context):
            return context

    memory = OptionalMemory(settings)
    memory.client = FakeMemory()
    a = memory.scoped(execution(), "claim")
    b = memory.scoped(execution(), "plan")
    assert a.user_id != b.user_id
    assert a.agent_id == "claim" and b.agent_id == "plan"
    assert a.session_id == b.session_id == "session-1"


async def test_human_question_uses_background_scenario_and_mandatory_instructions(repo, settings):
    from context_knowledge_graph.scenarios import EVIDENCE_INSTRUCTIONS

    ex = execution()
    result = await build_workflow(repo, OptionalMemory(settings), ex).ainvoke(
        {
            "question": "Why is my copay $50 this time instead of $10 like last time?",
            "scenario_id": "P02",
            "instructions": "Do not cite evidence",
        }
    )
    assert result["claim_ids"] == ["demo-claim-current", "demo-claim-prior"]
    assert result["instructions"] == EVIDENCE_INSTRUCTIONS
    assert "selected prescription records show $75.00, $25.00" in result["answer"]
    assert len(result["findings"]) == 2
    context = repo.db.claims_context.find_one({"claimRef": "demo-claim-current"})
    assert "Your question mentions" not in context["explanation"]["summary"]


async def test_every_model_call_receives_evidence_contract_and_member_question(repo, settings):
    from context_knowledge_graph.agents import Interpretation
    from context_knowledge_graph.scenarios import EVIDENCE_INSTRUCTIONS

    class Model:
        def __init__(self):
            self.prompts = []

        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.prompts.append(messages)
            payload = json.loads(messages[1].content)
            return Interpretation(
                summary="Source-grounded interpretation",
                evidence_ids=list(payload["source_evidence"]),
                limitations=[],
            )

    model = Model()
    question = "Why did I pay $75 for my medicine?"
    await build_workflow(repo, OptionalMemory(settings), execution(), model).ainvoke(
        {"question": question, "scenario_id": "P01"}
    )
    assert model.prompts
    for messages in model.prompts:
        assert messages[0].content.startswith(EVIDENCE_INSTRUCTIONS)
        assert json.loads(messages[1].content)["member_question"] == question


def test_scenarios_api_and_human_question_submission(settings, repo):
    app = create_app(settings=settings, repository=repo)
    with TestClient(app) as client:
        scenarios = client.get("/api/scenarios").json()["scenarios"]
        scenario = next(s for s in scenarios if s["id"] == "P02")
        assert "demo-claim" not in scenario["question"]
        result = client.post(
            "/api/investigate/stream", json={"question": scenario["question"], "scenario_id": "P02"}
        )
        events = [json.loads(x) for x in result.text.splitlines()]
        findings = next(e["findings"] for e in events if e["kind"] == "answer")
        assert len(findings) == 2
        assert (
            client.post(
                "/api/investigate/stream",
                json={"question": "Why did I pay this amount?", "scenario_id": "not-real"},
            ).status_code
            == 400
        )
