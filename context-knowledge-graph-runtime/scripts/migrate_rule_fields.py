"""Flatten rule metadata and remove obsolete ref fields; dry-run unless --apply."""

import argparse
import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository, digest


def transformed(document):
    metadata = document.get("meta", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"Non-document meta: {document['_id']}")
    result = deepcopy(document)
    for key, value in metadata.items():
        if key in {"_id", "meta", "ref"} or "." in key or key.startswith("$"):
            raise ValueError(f"Invalid metadata field: {key}")
        if key in document and digest(document[key]) != digest(value):
            raise ValueError(f"Root/meta collision: {document['_id']} / {key}")
        result[key] = deepcopy(value)
    result.pop("meta", None)
    result.pop("ref", None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        if repo.db.name != "context_knowledge_graph_demo":
            raise ValueError("This migration targets context_knowledge_graph_demo only")
        names = repo.db.list_collection_names()
        candidates = [name for name in ["ruleSets", "rulesSets"] if name in names]
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous or absent rule collection: {candidates}")
        name = candidates[0]
        collection = repo.db[name]
        before = list(collection.find({}).sort("_id", 1))
        if not before:
            raise ValueError("Rule collection is empty")
        after = [transformed(document) for document in before]
        affected = [d for d in before if "ref" in d or "meta" in d]
        indexes = list(collection.list_indexes())
        if any(
            key == "meta" or key.startswith("meta.") or key == "ref" or key.startswith("ref.")
            for index in indexes
            for key in index["key"]
        ):
            raise ValueError("Legacy field indexes require an explicit index migration")
        metadata_fields = sorted({key for d in before for key in d.get("meta", {})})
        report = {
            "database": repo.db.name,
            "collection": name,
            "mode": "apply" if args.apply else "dry-run",
            "documents": len(before),
            "documentsToChange": len(affected),
            "fieldsMovedToRoot": metadata_fields,
            "relationshipsPresent": sum("relationships" in d for d in before),
            "observedAt": datetime.now(UTC).isoformat(),
        }
        print(json.dumps(report), flush=True)
        if args.apply and affected:
            migration_id = "rule-root-fields-" + uuid4().hex
            archive = repo.client.context_knowledge_graph_archive
            backup_name = "rule_schema_backups"
            if backup_name not in archive.list_collection_names():
                archive.create_collection(backup_name)
            stamp = datetime.now(UTC)

            def transaction(session):
                current = list(collection.find({}, session=session).sort("_id", 1))
                if digest(current) != digest(before):
                    raise RuntimeError("Rules changed after preflight; aborting migration")
                archive[backup_name].insert_many(
                    [
                        {
                            "_id": migration_id + ":" + str(document["_id"]),
                            "migrationId": migration_id,
                            "database": repo.db.name,
                            "collection": name,
                            "originalId": document["_id"],
                            "archivedAt": stamp,
                            "document": deepcopy(document),
                        }
                        for document in affected
                    ],
                    session=session,
                )
                result = collection.update_many(
                    {"_id": {"$in": [d["_id"] for d in affected]}},
                    [
                        {"$replaceWith": {"$mergeObjects": ["$$ROOT", {"$ifNull": ["$meta", {}]}]}},
                        {"$unset": ["meta", "ref"]},
                    ],
                    session=session,
                )
                if result.matched_count != len(affected):
                    raise RuntimeError("Unexpected matched document count")
                actual = list(collection.find({}, session=session).sort("_id", 1))
                if digest(actual) != digest(after):
                    raise RuntimeError("Transformed documents differ from expected contents")

            with repo.client.start_session() as session:
                session.with_transaction(transaction)
            actual = list(collection.find({}).sort("_id", 1))
            if digest(actual) != digest(after):
                raise RuntimeError("Post-commit verification failed")
            backups = list(archive[backup_name].find({"migrationId": migration_id}))
            originals = sorted([item["document"] for item in backups], key=lambda d: d["_id"])
            if digest(originals) != digest(affected):
                raise RuntimeError("Archived originals differ from pre-migration documents")
            if list(collection.list_indexes()) != indexes:
                raise RuntimeError("Collection indexes changed unexpectedly")
            report.update(
                verified=True,
                migrationId=migration_id,
                modifiedDocuments=len(affected),
                archivedDocuments=len(backups),
                backupCollection=f"{archive.name}.{backup_name}",
                preservedFields=["_id", "ruleId", "ruleData", "relationships"],
                refRemaining=collection.count_documents({"ref": {"$exists": True}}),
                metaRemaining=collection.count_documents({"meta": {"$exists": True}}),
            )
            (ROOT / "data" / "rule-root-fields-migration-report.json").write_text(
                json.dumps(report, indent=2)
            )
        elif args.apply:
            report.update(verified=True, modifiedDocuments=0)
        print(json.dumps(report), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
