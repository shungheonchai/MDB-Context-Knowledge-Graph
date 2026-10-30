from copy import deepcopy

import pytest
from test_workflow import investigate

from context_knowledge_graph.context_schema import (
    mirror_document,
    rewrite_references,
    source_projection,
)
from context_knowledge_graph.repository import digest


def test_legacy_wrapper_mirrors_every_raw_field_and_keeps_additions():
    raw = {
        "_id": "plan-v2",
        "schemaVersion": 7,
        "version": 2,
        "benefit": {"price": 7500},
        "provenance": {"synthetic": True},
        "context": {"sourceNote": "Original annotation"},
    }
    old = {
        "_id": "context-plan-v2",
        "schemaVersion": 1,
        "revision": 3,
        "planRef": "plan-v2",
        "operationalSnapshot": {"version": 2, "benefit": {"price": 7500}},
        "source": {"documentId": "plan-v2"},
        "investigation": {"status": "complete", "findings": [{"summary": "Keep"}]},
        "metadata": {"note": {"statement": "Member reported a move"}},
        "customAddition": {"keep": True},
    }
    before = deepcopy(old)
    result = mirror_document(raw, old, "plans", "demo", "planRef", digest(raw))
    assert source_projection(result, raw) == raw
    assert result["_id"] == "plan-v2" and result["schemaVersion"] == 7
    assert result["contextSchemaVersion"] == 2 and result["revision"] == 4
    assert result["metadata"] == old["metadata"] and result["investigation"] == old["investigation"]
    assert result["customAddition"] == old["customAddition"]
    assert "operationalSnapshot" not in result
    assert old == before


def test_source_field_collision_is_not_silently_overwritten():
    with pytest.raises(ValueError, match="collision"):
        mirror_document(
            {"_id": "x", "investigation": {"sourceOwned": True}},
            None,
            "claims",
            "demo",
            "claimRef",
            "hash",
        )


def test_reference_rewrite_preserves_evidence_hash_values():
    original = {
        "evidenceHashes": {"demo.claims_context/context-x#source:t": "hash-value"},
        "summary": "Read demo.claims_context/context-x#source:t",
    }
    result = rewrite_references(
        original, {"demo.claims_context/context-x#": "demo.claims_context/x#"}
    )
    assert result["evidenceHashes"] == {"demo.claims_context/x#source:t": "hash-value"}
    assert original["evidenceHashes"].get("demo.claims_context/context-x#source:t") == "hash-value"


async def test_runtime_writes_root_source_fields_without_wrapper(repo, settings):
    before = deepcopy(repo.db.claims.find_one({"_id": "demo-claim-current"}))
    await investigate(repo, settings, "demo-claim-current")
    context = repo.db.claims_context.find_one({"_id": "demo-claim-current"})
    assert source_projection(context, before) == before
    assert "operationalSnapshot" not in context
    assert context["contextSchemaVersion"] == 2
    assert repo.db.claims.find_one({"_id": "demo-claim-current"}) == before


async def test_refresh_preserves_notes_and_removes_deleted_source_fields(repo, settings):
    repo.db.claims.update_one(
        {"_id": "demo-claim-current"}, {"$set": {"sourceExtra": {"value": 1}}}
    )
    await investigate(repo, settings, "demo-claim-current")
    repo.db.claims_context.update_one(
        {"_id": "demo-claim-current"}, {"$set": {"metadata": {"note": "Keep me"}}}
    )
    repo.db.claims.update_one({"_id": "demo-claim-current"}, {"$unset": {"sourceExtra": ""}})
    await investigate(repo, settings, "demo-claim-current")
    context = repo.db.claims_context.find_one({"_id": "demo-claim-current"})
    assert "sourceExtra" not in context
    assert context["metadata"] == {"note": "Keep me"}
