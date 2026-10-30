from datetime import datetime, timezone

import mongomock
import pytest

from context_knowledge_graph.config import Settings
from context_knowledge_graph.repository import Repository


def day(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def settings():
    # In-memory tests must not inherit credentials or write flags from local .env.
    return Settings(
        mongo_uri="mongodb://unused",
        database="context_knowledge_graph_demo",
        lexical_index="context_knowledge_graph_rules_lexical",
        llm_key="",
        use_llm=False,
        enable_context_writes=True,
        demo_mode=True,
        max_runs=4,
        run_timeout=180,
        memory_url="",
        memory_project="",
        memory_token="",
    )


@pytest.fixture
def repo(settings):
    db = mongomock.MongoClient(tz_aware=True).context_knowledge_graph_demo
    p = {"synthetic": True, "sourceSystem": "test"}
    db.members.insert_one(
        {
            "_id": "member-1",
            "provenance": p,
            "identifiers": {
                "sourceSystem": "test",
                "subscriberId": "sub-1",
                "personCode": "01",
                "clientCode": "test",
            },
            "coverage": [
                {"planCode": "PLAN", "from": day("2026-01-01"), "thru": day("2027-01-01")}
            ],
        }
    )
    db.drugs.insert_one(
        {
            "_id": "drug-1",
            "provenance": p,
            "product": {"productCode": "DRUG", "codeSystem": "test", "isGeneric": True},
        }
    )
    for version, cents, classification, start, end in [
        (1, 2500, "standard", "2026-01-01", "2026-10-01"),
        (2, 7500, "premium", "2026-10-01", None),
    ]:
        db.plans.insert_one(
            {
                "_id": f"plan-{version}",
                "provenance": p,
                "planCode": "PLAN",
                "version": version,
                "validFrom": day(start),
                "validTo": day(end) if end else None,
                "benefit": {
                    "daysSupply": 30,
                    "channel": "retail",
                    "drugRules": [
                        {
                            "ruleId": f"rule-{version}",
                            "drugRef": "drug-1",
                            "classification": classification,
                            "memberCostCents": cents,
                        }
                    ],
                },
            }
        )
        db.rules_policies.insert_one(
            {
                "_id": f"policy-{version}",
                "provenance": p,
                "version": version,
                "scope": {"planRef": f"plan-{version}"},
                "content": {"summary": "Test rule reference"},
            }
        )
    db.prior_authorizations.insert_one(
        {
            "_id": "pa-1",
            "provenance": p,
            "memberRef": "member-1",
            "drugRef": "drug-1",
            "validFrom": day("2026-10-01"),
            "validTo": day("2027-01-01"),
            "decision": {
                "status": "approved",
                "scope": "coverage-only",
                "changesCostSharing": False,
            },
        }
    )
    for suffix in [
        "current",
        "prior",
        "pa",
        "missing-drug",
        "missing-plan",
        "missing-member",
        "missing-all-refs",
        "unresolved-identity",
        "no-pa",
        "conflict",
    ]:
        prior = suffix == "prior"
        c = {
            "_id": "demo-claim-" + suffix,
            "provenance": p,
            "memberRef": "member-1",
            "drugRef": "drug-1",
            "planRef": "plan-1" if prior else "plan-2",
            "serviceDate": day("2026-09-15" if prior else "2026-10-15"),
            "prescription": {"quantity": 30, "daysSupply": 30, "channel": "retail"},
            "priorAuthorization": {"status": "not-required"},
            "adjudication": {
                "memberPaidCents": 2500 if prior else 7500,
                "currency": "USD",
                "components": {"copayCents": 2500 if prior else 7500},
            },
        }
        missing = []
        if suffix == "missing-drug":
            missing = ["drugRef"]
        if suffix == "missing-plan":
            missing = ["planRef"]
        if suffix == "missing-member":
            missing = ["memberRef"]
        if suffix in ["missing-all-refs", "unresolved-identity"]:
            missing = ["memberRef", "drugRef", "planRef"]
        for k in missing:
            c.pop(k)
        if "memberRef" in missing and suffix != "unresolved-identity":
            c["submittedMember"] = {
                "sourceSystem": "test",
                "subscriberId": "sub-1",
                "personCode": "01",
                "clientCode": "test",
            }
        if "drugRef" in missing and suffix != "unresolved-identity":
            c["submittedDrug"] = {"productCode": "DRUG", "codeSystem": "test"}
        if suffix == "unresolved-identity":
            c["submittedMember"] = {"displayName": "Some person"}
            c["priorAuthorization"]["status"] = "unknown"
        if suffix == "pa":
            c["paRef"] = "pa-1"
        if suffix in ["prior", "current", "pa", "conflict"]:
            trace = "trace-" + c["_id"]
            c["adjudication"]["decisionTraceRef"] = trace
            db.client.context_knowledge_graph_archive.decision_traces.insert_one(
                {
                    "_id": trace,
                    "provenance": p,
                    "businessObject": {"type": "claim", "id": c["_id"]},
                    "events": [
                        {
                            "type": "rule-applied",
                            "ruleId": "rule-1" if prior else "rule-2",
                            "outcome": {
                                "classification": "standard" if prior else "premium",
                                "memberCostCents": 111
                                if suffix == "conflict"
                                else c["adjudication"]["memberPaidCents"],
                            },
                        }
                    ],
                }
            )
        db.claims.insert_one(c)
    return Repository(settings, database=db)
