"""Add versioned synthetic evidence dependencies for the copay graph depth demo."""

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from bson import ObjectId

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository, digest

TAG = "context-knowledge-graph-depth-demo-v1"
EFFECTIVE = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(9999, 12, 31, 23, 59, 59, 999000, tzinfo=UTC)
ROOT_ID = ObjectId("467618533fe0438a98b1dde9")
MAC_ID = ObjectId("467618533fe0438a98b1dde8")
# These are evidence-validation procedures, not additional monetary pricing formulas.
SPECS = [
    (
        "mac-selection",
        "Pricing",
        "MAC List Effective Version Selection",
        ["plan.macListId", "claim.fillDate"],
        ["mac-assignment", "mac-rate"],
    ),
    (
        "product-resolution",
        "Drug",
        "Drug Product Pricing Identifier Resolution",
        ["drug.ndc", "drug.gpi", "claim.productId"],
        ["crosswalk", "cost-components"],
    ),
    (
        "mac-assignment",
        "Plan",
        "Plan MAC List Assignment Verification",
        ["plan.macListId", "plan.benefitVersion"],
        ["benefit-version"],
    ),
    (
        "mac-rate",
        "Pricing",
        "Historical MAC Rate Selection",
        ["pricing.macPrice", "claim.fillDate"],
        ["price-history"],
    ),
    (
        "crosswalk",
        "Drug",
        "Drug NDC and GPI Crosswalk Verification",
        ["drug.ndc", "drug.gpi", "drug.packageId"],
        ["unit-normalization"],
    ),
    (
        "cost-components",
        "Pricing",
        "Submitted Prescription Cost Component Validation",
        ["claim.ingredientCost", "claim.dispensingFee", "claim.tax"],
        ["fee-validation", "unit-normalization"],
    ),
    (
        "benefit-version",
        "Plan",
        "Plan Benefit Effective Version Verification",
        ["plan.version", "plan.effectiveDate", "claim.fillDate"],
        ["coverage-segment"],
    ),
    (
        "price-history",
        "Drug",
        "Drug Price History Effective Record Verification",
        ["drug.priceHistory", "claim.fillDate"],
        ["price-provenance"],
    ),
    (
        "unit-normalization",
        "Drug",
        "Drug Package Pricing Unit Normalization",
        ["drug.packageSize", "claim.quantity", "pricing.unitBasis"],
        ["package-evidence"],
    ),
    (
        "fee-validation",
        "Pricing",
        "Dispensing Fee Component Validation",
        ["claim.dispensingFee", "pharmacy.networkType"],
        ["network-config"],
    ),
    (
        "coverage-segment",
        "Member",
        "Member Coverage Segment Selection",
        ["member.coverageHistory", "claim.fillDate"],
        ["coverage-election"],
    ),
    (
        "price-provenance",
        "Drug",
        "Drug Price Source Provenance Verification",
        ["drug.priceSource", "drug.pricePublicationId"],
        ["publication-evidence"],
    ),
    (
        "package-evidence",
        "Drug",
        "Drug Package Reference Evidence Verification",
        ["drug.packageReferenceId", "drug.catalogVersion"],
        ["catalog-revision"],
    ),
    (
        "network-config",
        "Plan",
        "Pharmacy Network Reimbursement Configuration Verification",
        ["pharmacy.networkId", "plan.contractId", "claim.fillDate"],
        ["contract-version", "benefit-version"],
    ),
    (
        "coverage-election",
        "Member",
        "Member Coverage Election Source Evidence",
        ["member.coverageElectionId", "member.coverageSourceVersion"],
        [],
    ),
    (
        "publication-evidence",
        "Pricing",
        "Historical Drug Price Publication Evidence",
        ["pricing.publicationId", "pricing.publicationEffectiveDate"],
        [],
    ),
    (
        "catalog-revision",
        "Drug",
        "Drug Product Catalog Revision Evidence",
        ["drug.catalogVersion", "drug.catalogEffectiveDate"],
        [],
    ),
    (
        "contract-version",
        "Plan",
        "Pharmacy Contract Effective Version Evidence",
        ["plan.contractId", "plan.contractVersion", "claim.fillDate"],
        [],
    ),
]


def object_id(key):
    return ObjectId(hashlib.sha256(f"{TAG}:{key}".encode()).hexdigest()[:24])


def traversal(collection, date, max_depth):
    applicable = {"effStartDate": {"$lte": date}, "effEndDate": {"$gt": date}}
    rows = list(
        collection.aggregate(
            [
                {"$match": {"ruleId": ROOT_ID, "entryPoint": True, **applicable}},
                {
                    "$graphLookup": {
                        "from": "rulesSets",
                        "startWith": "$ruleId",
                        "connectFromField": "relationships.targetRuleId",
                        "connectToField": "ruleId",
                        "as": "g",
                        "maxDepth": max_depth,
                        "depthField": "depth",
                        "restrictSearchWithMatch": applicable,
                    }
                },
                {"$project": {"g": 1}},
            ],
            maxTimeMS=20000,
        )
    )
    assert len(rows) == 1, "Ambiguous or missing root version"
    return rows[0]["g"]


def verify_graph(rows, date):
    applicable = [d for d in rows if d["effStartDate"] <= date < d["effEndDate"]]
    by_id = {}
    for document in applicable:
        by_id.setdefault(document["ruleId"], []).append(document)
    for key, versions in by_id.items():
        assert len(versions) == 1, f"Overlapping versions: {key}"
    graph = {}
    for document in applicable:
        targets = [edge["targetRuleId"] for edge in document.get("relationships", [])]
        assert all(t in by_id for t in targets), f"Dangling relationship: {document['_id']}"
        graph[document["ruleId"]] = targets
    visiting, done = set(), set()

    def visit(key):
        assert key not in visiting, "Relationship cycle"
        if key in done:
            return
        visiting.add(key)
        for target in graph.get(key, []):
            visit(target)
        visiting.remove(key)
        done.add(key)

    visit(ROOT_ID)
    distances, frontier = {ROOT_ID: 0}, [ROOT_ID]
    while frontier:
        key = frontier.pop(0)
        for target in graph.get(key, []):
            if target not in distances:
                distances[target] = distances[key] + 1
                frontier.append(target)
    return {str(depth): sum(value <= depth for value in distances.values()) for depth in range(8)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        assert repo.db.name == "context_knowledge_graph_demo"
        collection = repo.db.rulesSets
        before = list(collection.find({}).sort("_id", 1))
        if any(d["_id"] == object_id("mac-version-3") for d in before):
            assert verify_graph(before, datetime(2026, 10, 15, tzinfo=UTC))["7"] == 26
            print(json.dumps({"alreadyApplied": True, "documentsToWrite": 0}))
            return
        versions = [d for d in before if d["ruleId"] == MAC_ID]
        assert len(versions) == 1 and versions[0]["version"] == 2
        previous = versions[0]
        assert previous["effStartDate"] < EFFECTIVE < previous["effEndDate"]
        assert not previous.get("relationships"), "MAC relationships changed; review expansion"
        closed = deepcopy(previous)
        closed["effEndDate"] = EFFECTIVE
        next_version = deepcopy(previous)
        next_version.update(_id=object_id("mac-version-3"), version=3, effStartDate=EFFECTIVE)
        next_version["relationships"] = [
            {"relationship": "requires", "targetRuleId": object_id(key)}
            for key in ["mac-selection", "product-resolution"]
        ]
        next_version["provenance"] = {
            "synthetic": True,
            "fixtureSet": TAG,
            "supersedesDocumentId": previous["_id"],
            "note": "Synthetic graph traversal example; not an approved healthcare policy.",
        }
        next_version["updatedBy"] = "Context Knowledge Graph synthetic fixture generator"
        inserted = [next_version]
        for key, domain, title, fields, dependencies in SPECS:
            instruction = f"Verify {title.lower()} using the referenced source evidence applicable on the claim fill date. Report missing evidence instead of inventing values."
            inserted.append(
                {
                    "_id": object_id(key),
                    "ruleId": object_id(key),
                    "ruleDomain": domain,
                    "ruleName": title,
                    "ruleType": "EvidenceValidation",
                    "ruleSubType": key,
                    "ruleData": {
                        "evaluationMode": "evidence-validation",
                        "instruction": instruction,
                        "dataElementsNeeded": fields,
                    },
                    "ruleDataText": instruction
                    + " Required data elements: "
                    + ", ".join(fields)
                    + ".",
                    "entryPoint": False,
                    "purpose": "traversal-strategy",
                    "strategyId": TAG,
                    "relationships": [
                        {"relationship": "requires", "targetRuleId": object_id(target)}
                        for target in dependencies
                    ],
                    "version": 1,
                    "active": True,
                    "effStartDate": EFFECTIVE,
                    "effEndDate": END,
                    "createdBy": "Context Knowledge Graph synthetic fixture generator",
                    "updatedBy": "Context Knowledge Graph synthetic fixture generator",
                    "provenance": {
                        "synthetic": True,
                        "fixtureSet": TAG,
                        "note": "Synthetic graph traversal example; not an approved healthcare policy.",
                    },
                }
            )
        assert not ({d["_id"] for d in before} & {d["_id"] for d in inserted})
        expected = sorted(
            [closed if d["_id"] == previous["_id"] else deepcopy(d) for d in before] + inserted,
            key=lambda d: d["_id"],
        )
        date = datetime(2026, 10, 15, tzinfo=UTC)
        historical_date = datetime(2026, 9, 15, tzinfo=UTC)
        counts = verify_graph(expected, date)
        assert list(counts.values()) == [1, 7, 8, 10, 14, 18, 22, 26]
        assert verify_graph(before, historical_date) == verify_graph(expected, historical_date)
        historical_before = traversal(collection, historical_date, 7)
        report = {
            "mode": "apply" if args.apply else "dry-run",
            "insertedRuleVersions": len(inserted),
            "existingVersionsToClose": 1,
            "effectiveFrom": EFFECTIVE.isoformat(),
            "expectedCountsByMaxDepth": counts,
            "historicalGraphCount": len(historical_before),
            "totalRulesAfter": len(expected),
        }
        print(json.dumps(report), flush=True)
        if args.apply:
            archive = repo.client.context_knowledge_graph_archive
            if "rule_schema_backups" not in archive.list_collection_names():
                archive.create_collection("rule_schema_backups")
            run_id = TAG + "-" + uuid4().hex

            def transaction(session):
                assert digest(list(collection.find({}, session=session).sort("_id", 1))) == digest(
                    before
                ), "Rules changed since preflight"
                archive.rule_schema_backups.insert_one(
                    {
                        "_id": run_id + ":" + str(previous["_id"]),
                        "migrationId": run_id,
                        "database": repo.db.name,
                        "collection": "rulesSets",
                        "originalId": previous["_id"],
                        "archivedAt": datetime.now(UTC),
                        "document": deepcopy(previous),
                    },
                    session=session,
                )
                collection.replace_one({"_id": previous["_id"]}, closed, session=session)
                collection.insert_many(inserted, session=session)
                assert digest(list(collection.find({}, session=session).sort("_id", 1))) == digest(
                    expected
                )

            with repo.client.start_session() as session:
                session.with_transaction(transaction)
            assert digest(list(collection.find({}).sort("_id", 1))) == digest(expected)
            observed = {}
            for depth in range(8):
                graph = traversal(collection, date, depth)
                assert len(graph) == counts[str(depth)]
                assert all(int(d["depth"]) <= depth for d in graph)
                observed[str(depth)] = len(graph)
            historical_after = traversal(collection, historical_date, 7)

            def key(document):
                return document["_id"]

            assert digest(sorted(historical_before, key=key)) != digest(
                sorted(historical_after, key=key)
            )  # MAC version's end date was closed.

            def historical_content(graph):
                result = []
                for row in graph:
                    row = deepcopy(row)
                    if row["_id"] == previous["_id"]:
                        row["effEndDate"] = previous["effEndDate"]
                    result.append(row)
                return sorted(result, key=key)

            assert digest(historical_content(historical_before)) == digest(
                historical_content(historical_after)
            )
            report.update(
                verified=True,
                migrationId=run_id,
                observedCountsByMaxDepth=observed,
                historicalGraphContentPreserved=True,
                backupCollection="context_knowledge_graph_archive.rule_schema_backups",
                insertedDocumentIds=[str(d["_id"]) for d in inserted],
            )
            (ROOT / "data" / "rule-graph-expansion-report.json").write_text(
                json.dumps(report, indent=2)
            )
            print(json.dumps(report), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
