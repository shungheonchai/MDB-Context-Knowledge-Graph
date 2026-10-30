"""Inspect or add purpose/date prefilters without changing embedding configuration."""

import argparse
import json
import time
from copy import deepcopy

from pymongo.operations import SearchIndexModel

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository, plain
from context_knowledge_graph.retrieval import VECTOR_INDEX

FILTER_PATHS = ("purpose", "effStartDate", "effEndDate")


def with_prefilters(definition):
    updated = deepcopy(definition)
    fields = updated.get("fields", [])
    if not any(f.get("type") == "autoEmbed" and f.get("path") == "ruleDataText" for f in fields):
        raise ValueError("Expected an autoEmbed index on ruleDataText; no changes made")
    for path in FILTER_PATHS:
        matches = [f for f in fields if f.get("path") == path]
        if matches and any(f.get("type") != "filter" for f in matches):
            raise ValueError(f"Incompatible definition for {path}; no changes made")
        if not matches:
            fields.append({"type": "filter", "path": path})
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create/update the vector index")
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        collection = repo.db.rulesSets
        existing = next(
            (i for i in collection.list_search_indexes() if i["name"] == VECTOR_INDEX), None
        )
        if existing and existing.get("type") != "vectorSearch":
            raise ValueError("The index name belongs to a different index type")
        before = existing["latestDefinition"] if existing else None
        asset = json.loads((ROOT / "demo/hybrid-search/vector-index.json").read_text())
        desired = with_prefilters(before if before is not None else asset["definition"])
        print(
            json.dumps(
                {
                    "index": VECTOR_INDEX,
                    "mode": "apply" if args.apply else "preflight",
                    "changesNeeded": before != desired,
                    "definition": desired,
                }
            )
        )
        if not args.apply:
            return
        if before != desired:
            directory = ROOT / "data"
            directory.mkdir(exist_ok=True)
            backup = directory / f"vector-index-before-prefilters-{time.time_ns()}.json"
            backup.write_text(
                json.dumps(plain({"name": VECTOR_INDEX, "definition": before}), indent=2)
            )
            if existing:
                collection.update_search_index(VECTOR_INDEX, desired)
            else:
                collection.create_search_index(
                    SearchIndexModel(name=VECTOR_INDEX, type="vectorSearch", definition=desired)
                )
        deadline = time.monotonic() + 300
        last_log = 0
        while time.monotonic() < deadline:
            current = next(
                (i for i in collection.list_search_indexes() if i["name"] == VECTOR_INDEX), None
            )
            if current and current.get("status") == "FAILED":
                raise RuntimeError("Vector index build failed; inspect Atlas Search status")
            # READY ensures the new definition has finished building, not just that
            # an older index generation remains queryable during the update.
            if (
                current
                and current.get("status") == "READY"
                and current.get("queryable")
                and current.get("latestDefinition") == desired
            ):
                print("Vector index READY with purpose/date prefilters.")
                return
            if time.monotonic() - last_log > 10:
                print("Waiting for vector index to become READY...", flush=True)
                last_log = time.monotonic()
            time.sleep(2)
        raise TimeoutError(
            "Index update submitted but not READY within five minutes; inspect Atlas before using new filters"
        )
    finally:
        repo.close()


if __name__ == "__main__":
    main()
