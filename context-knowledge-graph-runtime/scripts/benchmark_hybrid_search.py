"""Read-only exact/ANN comparison on both questions; not a production load benchmark."""

import argparse
import json
import time
from pathlib import Path

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository
from context_knowledge_graph.retrieval import CASES, PROFILES, make_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Optional pre-change comparison JSON")
    parser.add_argument("--num-candidates", type=int, default=1000)
    args = parser.parse_args()
    if not 50 <= args.num_candidates <= 10000:
        parser.error("num-candidates must be between 50 and 10000")
    baseline = {}
    if args.baseline:
        for record in json.loads(args.baseline.read_text())["comparisons"]:
            baseline[(record["case"], record["profile"])] = record
    repo = Repository(Settings())
    try:
        collection = repo.db.rulesSets
        count = collection.count_documents({})
        records = []
        for case in CASES:
            claims = [
                repo.db.claims.find_one({"_id": key, "provenance.synthetic": True})
                for key in case["claim_ids"]
            ]
            exact = {}
            for profile in PROFILES:
                for mode in ["exact", "ann"]:
                    pipeline, _ = make_pipeline(
                        case,
                        claims,
                        profile,
                        count,
                        vector_mode=mode,
                        num_candidates=args.num_candidates,
                    )
                    query = pipeline[0]["$rankFusion"]["input"]["pipelines"]["vector"][0][
                        "$vectorSearch"
                    ]
                    started = time.perf_counter()
                    rows = list(
                        collection.aggregate([pipeline[0], {"$limit": 20}], maxTimeMS=45000)
                    )
                    ids = [str(row["_id"]) for row in rows]
                    record = {
                        "case": case["id"],
                        "profile": profile,
                        "mode": mode,
                        "elapsedMs": round((time.perf_counter() - started) * 1000),
                        "ids": ids,
                        "eligibleVersions": collection.count_documents(query["filter"]),
                    }
                    if mode == "exact":
                        exact[profile] = ids
                        old = baseline.get((case["id"], profile))
                        if old:
                            record["baselineSameOrder"] = ids == old["ids"]
                            record["baselineSameSet"] = set(ids) == set(old["ids"])
                            record["baselineElapsedMs"] = old["elapsedMs"]
                    else:
                        reference = exact[profile]
                        record["sameOrderAsExact"] = ids == reference
                        record["overlapWithExact"] = (
                            len(set(ids) & set(reference)) / len(reference) if reference else None
                        )
                    records.append(record)
                    print(
                        json.dumps({key: value for key, value in record.items() if key != "ids"}),
                        flush=True,
                    )
        output = ROOT / "data/hybrid-performance-comparison.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "note": "Single-run hybrid top-20 comparison, not vector-only recall or a throughput benchmark. Latency includes embedding, network, and cache effects.",
                    "comparisons": records,
                },
                indent=2,
            )
        )
        print("Report:", output.relative_to(ROOT))
    finally:
        repo.close()


if __name__ == "__main__":
    main()
