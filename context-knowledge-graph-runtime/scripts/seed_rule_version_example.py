"""Create an isolated three-version rule example without changing demo graph membership."""

import argparse
import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from bson import ObjectId

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository, digest, plain

RULE_ID = ObjectId("467618533fe0438a98b1dde4")
TAG = "isolated-rule-version-example-v1"
DATES = [
    datetime(2026, 1, 1, tzinfo=UTC),
    datetime(2026, 5, 1, tzinfo=UTC),
    datetime(2026, 9, 1, tzinfo=UTC),
]
CAPS = [150, 125, 100]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        assert repo.db.name == "context_knowledge_graph_demo"
        collection = repo.db.rulesSets
        before = list(collection.find({}).sort("_id", 1))
        versions = sorted([d for d in before if d["ruleId"] == RULE_ID], key=lambda d: d["version"])
        if len(versions) == 3:
            assert [d["version"] for d in versions] == [1, 2, 3]
            assert [d["effStartDate"] for d in versions] == DATES
            assert [d["ruleData"]["maxDispensingFee"] for d in versions] == CAPS
            assert versions[0]["effEndDate"] == DATES[1] and versions[1]["effEndDate"] == DATES[2]
            print(json.dumps({"alreadyApplied": True, "documentsToWrite": 0}))
            return
        assert len(versions) == 1 and versions[0]["version"] == 1
        old = versions[0]
        assert old["effStartDate"] == DATES[0] and old["effEndDate"] > DATES[-1]
        assert old.get("entryPoint") is not True
        assert old.get("purpose") != "traversal-strategy"
        assert not old.get("relationships")
        assert collection.count_documents({"relationships.targetRuleId": RULE_ID}) == 0
        closed = deepcopy(old)
        closed["effEndDate"] = DATES[1]
        inserted = []
        for version in [2, 3]:
            value = deepcopy(old)
            value.update(
                _id=ObjectId(),
                version=version,
                effStartDate=DATES[version - 1],
                effEndDate=DATES[version] if version < 3 else old["effEndDate"],
                updatedBy="Context Knowledge Graph synthetic version example",
            )
            value["ruleData"]["maxDispensingFee"] = CAPS[version - 1]
            value["ruleDataText"] = (
                f"Rule data specifies max dispensing fee is {CAPS[version - 1]}; requires specialty pharmacy is yes. Required data elements are claim.dispensing fee and drug.is specialty."
            )
            value["provenance"] = {
                "synthetic": True,
                "fixtureSet": TAG,
                "note": "Synthetic data-model example; not an approved healthcare policy.",
            }
            inserted.append(value)
        report = {
            "mode": "apply" if args.apply else "dry-run",
            "ruleId": str(RULE_ID),
            "ruleName": old["ruleName"],
            "insertedVersions": 2,
            "updatedOriginalVersions": 1,
            "entryPoint": False,
            "incomingRelationships": 0,
            "versions": plain([closed] + inserted),
        }
        print(json.dumps({k: v for k, v in report.items() if k != "versions"}), flush=True)
        if args.apply:
            archive = repo.client.context_knowledge_graph_archive
            if "rule_schema_backups" not in archive.list_collection_names():
                archive.create_collection("rule_schema_backups")
            run_id = TAG + "-" + uuid4().hex
            expected = sorted(
                [closed if d["_id"] == old["_id"] else d for d in before] + inserted,
                key=lambda d: d["_id"],
            )

            def transaction(session):
                assert digest(list(collection.find({}, session=session).sort("_id", 1))) == digest(
                    before
                )
                archive.rule_schema_backups.insert_one(
                    {
                        "_id": run_id + ":" + str(old["_id"]),
                        "migrationId": run_id,
                        "database": repo.db.name,
                        "collection": "rulesSets",
                        "originalId": old["_id"],
                        "archivedAt": datetime.now(UTC),
                        "document": deepcopy(old),
                    },
                    session=session,
                )
                collection.update_one(
                    {"_id": old["_id"]}, {"$set": {"effEndDate": DATES[1]}}, session=session
                )
                collection.insert_many(inserted, session=session)
                assert digest(list(collection.find({}, session=session).sort("_id", 1))) == digest(
                    expected
                )

            with repo.client.start_session() as session:
                session.with_transaction(transaction)
            assert digest(list(collection.find({}).sort("_id", 1))) == digest(expected)
            for date, version in [
                (datetime(2026, 4, 30, tzinfo=UTC), 1),
                (DATES[1], 2),
                (datetime(2026, 8, 31, tzinfo=UTC), 2),
                (DATES[2], 3),
                (datetime(2026, 10, 15, tzinfo=UTC), 3),
            ]:
                found = list(
                    collection.find(
                        {
                            "ruleId": RULE_ID,
                            "effStartDate": {"$lte": date},
                            "effEndDate": {"$gt": date},
                        }
                    )
                )
                assert len(found) == 1 and found[0]["version"] == version
            # Both kinds of rule discovery retain exactly the same eligible documents.
            for query in [{"entryPoint": True}, {"purpose": "traversal-strategy"}]:
                previous = [d for d in before if all(d.get(k) == v for k, v in query.items())]
                assert digest(list(collection.find(query).sort("_id", 1))) == digest(previous)
            report.update(
                verified=True,
                migrationId=run_id,
                totalRuleDocuments=len(expected),
                demoEntryPointsAndCuratedRulesUnchanged=True,
                backupCollection="context_knowledge_graph_archive.rule_schema_backups",
            )
            (ROOT / "data" / "isolated-rule-versions-report.json").write_text(
                json.dumps(report, indent=2)
            )
            print(json.dumps({k: v for k, v in report.items() if k != "versions"}), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
