"""Dry-run-first migration. Only context collections and an archive backup are writable."""

import argparse
import json
from copy import deepcopy
from uuid import uuid4

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.context_schema import (
    mirror_document,
    rewrite_references,
    source_projection,
)
from context_knowledge_graph.models import DOMAINS, now
from context_knowledge_graph.repository import Repository, digest, plain


def plan(database):
    sources, contexts, operations, locations = {}, {}, [], {}
    for source, target, ref in DOMAINS.values():
        raw = list(database[source].find({}).sort("_id", 1))
        assert all(r.get("provenance", {}).get("synthetic") is True for r in raw), (
            "Non-synthetic source: " + source
        )
        old = list(database[target].find({}).sort("_id", 1))
        sources[source], contexts[target] = raw, old
        valid = {r["_id"] for r in raw}
        by_ref = {}
        for c in old:
            entity = c.get("source", {}).get("documentId", c.get(ref))
            if entity is None and c["_id"] in valid:
                entity = c["_id"]
            assert entity in valid, "Orphan context: " + str(c["_id"])
            assert entity not in by_ref, "Duplicate context for " + str(entity)
            by_ref[entity] = c
            if c["_id"] != entity:
                locations[f"{database.name}.{target}/{c['_id']}#"] = (
                    f"{database.name}.{target}/{entity}#"
                )
                locations[f"{target}/{c['_id']}#"] = f"{target}/{entity}#"
        for r in raw:
            previous = by_ref.get(r["_id"])
            if (
                previous
                and previous.get("contextSchemaVersion") == 2
                and "operationalSnapshot" not in previous
                and digest(source_projection(previous, r)) == digest(r)
            ):
                continue
            value = mirror_document(r, previous, source, database.name, ref, digest(r))
            if previous and previous.get("metadata") != value.get("metadata"):
                raise ValueError("Enrichment metadata changed: " + str(r["_id"]))
            if previous and previous.get("operationalSnapshot"):
                original = {k: v for k, v in r.items() if k not in {"_id", "context", "provenance"}}
                if digest(original) != digest(previous["operationalSnapshot"]):
                    value["freshness"]["enrichmentsStatus"] = "needs_revalidation"
            operations.append(
                {
                    "source": source,
                    "target": target,
                    "ref": ref,
                    "raw": r,
                    "previous": previous,
                    "value": value,
                }
            )
    for operation in operations:
        for field in ["investigation", "explanation", "resolvedRelationships"]:
            if field in operation["value"]:
                operation["value"][field] = rewrite_references(operation["value"][field], locations)
    return sources, contexts, operations, locations


def apply_plan(repo, sources, contexts, operations):
    if not operations:
        return None
    run_id = "context-mirror-v2-" + uuid4().hex
    archive = repo.client.context_knowledge_graph_archive
    if "context_mirror_backups" not in archive.list_collection_names():
        archive.create_collection("context_mirror_backups")

    def transaction(session):
        db = session.client[repo.db.name]
        # Abort before replacing anything if another writer has changed source or context.
        for source, expected in sources.items():
            assert digest(list(db[source].find({}, session=session).sort("_id", 1))) == digest(
                expected
            ), "Source changed: " + source
        for target, expected in contexts.items():
            assert digest(list(db[target].find({}, session=session).sort("_id", 1))) == digest(
                expected
            ), "Context changed: " + target
        for item in operations:
            target, old = item["target"], item["previous"]
            if old:
                session.client.context_knowledge_graph_archive.context_mirror_backups.insert_one(
                    {
                        "_id": run_id + ":" + target + ":" + str(old["_id"]),
                        "migrationId": run_id,
                        "database": db.name,
                        "collection": target,
                        "originalId": old["_id"],
                        "archivedAt": now(),
                        "document": deepcopy(old),
                    },
                    session=session,
                )
                if old["_id"] != item["value"]["_id"]:
                    db[target].delete_one({"_id": old["_id"]}, session=session)
            db[target].replace_one(
                {"_id": item["value"]["_id"]}, item["value"], upsert=True, session=session
            )
        for item in operations:
            actual = db[item["target"]].find_one({"_id": item["raw"]["_id"]}, session=session)
            assert "operationalSnapshot" not in actual
            assert digest(source_projection(actual, item["raw"])) == digest(item["raw"]), (
                "Mirror mismatch"
            )
            if item["previous"]:
                assert digest(actual.get("metadata")) == digest(item["previous"].get("metadata")), (
                    "Metadata mismatch"
                )
                assert digest(actual["investigation"]) == digest(item["value"]["investigation"]), (
                    "Lost investigation"
                )
        for source, expected in sources.items():
            assert digest(list(db[source].find({}, session=session).sort("_id", 1))) == digest(
                expected
            ), "Source modified"

    with repo.client.start_session() as session:
        session.with_transaction(transaction)
    return run_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        sources, contexts, operations, locations = plan(repo.db)
        report = {
            "observedAt": now(),
            "mode": "apply" if args.apply else "dry-run",
            "operationalCounts": {k: len(v) for k, v in sources.items()},
            "contextCountsBefore": {k: len(v) for k, v in contexts.items()},
            "documentsToWrite": len(operations),
            "documentsToArchive": sum(bool(o["previous"]) for o in operations),
            "documentsToInitialize": sum(o["previous"] is None for o in operations),
            "legacyReferenceLocations": len(locations),
        }
        print(json.dumps(report), flush=True)
        if args.apply:
            report["migrationId"] = apply_plan(repo, sources, contexts, operations)
            for source, target, ref in DOMAINS.values():
                repo.db[target].create_index([(ref, 1)], unique=True, name="ux_domain_object")
                for raw in sources[source]:
                    mirrored = repo.db[target].find_one({"_id": raw["_id"]})
                    assert mirrored and "operationalSnapshot" not in mirrored
                    assert digest(source_projection(mirrored, raw)) == digest(raw)
                assert repo.db[target].count_documents({}) == len(sources[source])
                assert digest(list(repo.db[source].find({}).sort("_id", 1))) == digest(
                    sources[source]
                )
            report["verified"] = True
            report["operationalRecordsUnchanged"] = True
            report["contextCountsAfter"] = {
                target: repo.db[target].count_documents({}) for _, target, _ in DOMAINS.values()
            }
            report["backupCollection"] = "context_knowledge_graph_archive.context_mirror_backups"
        (ROOT / "data").mkdir(exist_ok=True)
        filename = (
            "context-mirror-migration-report.json"
            if args.apply
            else "context-mirror-preflight.json"
        )
        (ROOT / "data" / filename).write_text(json.dumps(plain(report), indent=2))
        print(json.dumps(report), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
