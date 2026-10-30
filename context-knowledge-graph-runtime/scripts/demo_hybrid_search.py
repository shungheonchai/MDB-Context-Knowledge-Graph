"""Compare two member questions across three real Atlas hybrid retrieval profiles."""

import argparse
import json
import time
from datetime import UTC, datetime

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.repository import Repository, plain
from context_knowledge_graph.retrieval import (
    CASES,
    LEXICAL_INDEX,
    PROFILES,
    VECTOR_INDEX,
    make_pipeline,
    shell,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=[case["id"] for case in CASES])
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--vector-mode", choices=["exact", "ann"], default="exact")
    parser.add_argument("--num-candidates", type=int, default=1000)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Export pipelines without issuing search queries",
    )
    args = parser.parse_args()
    repo = Repository(Settings())
    try:
        collection = repo.db.rulesSets
        indexes = list(collection.list_search_indexes())
        ready = {item["name"] for item in indexes if item.get("queryable")}
        if not args.prepare_only and not {LEXICAL_INDEX, VECTOR_INDEX} <= ready:
            raise RuntimeError(
                f"Queryable indexes required: {LEXICAL_INDEX}, {VECTOR_INDEX}; ready: {sorted(ready)}"
            )
        output = ROOT / "data" / "hybrid-demo"
        output.mkdir(parents=True, exist_ok=True)
        reports = []
        count = collection.count_documents({})
        for case in CASES:
            if args.case and args.case != case["id"]:
                continue
            claims = [
                repo.db.claims.find_one({"_id": claim_id, "provenance.synthetic": True})
                for claim_id in case["claim_ids"]
            ]
            assert all(claims), "Missing authorized demo claim"
            for profile in PROFILES:
                if args.profile and args.profile != profile:
                    continue
                pipeline, config = make_pipeline(
                    case,
                    claims,
                    profile,
                    count,
                    vector_mode=args.vector_mode,
                    num_candidates=args.num_candidates,
                )
                filename = output / f"{case['id']}-{profile}.compass.js"
                filename.write_text(shell(pipeline) + "\n")
                started = time.perf_counter()
                results = (
                    list(collection.aggregate(pipeline, maxTimeMS=60000))
                    if not args.prepare_only
                    else []
                )
                report = {
                    "case": case["id"],
                    "question": case["question"],
                    "profile": profile,
                    "config": config,
                    "claimIds": case["claim_ids"],
                    "claimFacts": plain(claims),
                    "results": plain(results),
                    "elapsedMs": round((time.perf_counter() - started) * 1000),
                    "pipelineFile": str(filename),
                    "executed": not args.prepare_only,
                }
                reports.append(report)
                print(
                    json.dumps(
                        {
                            "case": case["id"],
                            "profile": profile,
                            "executed": report["executed"],
                            "topRules": [item["ruleName"] for item in results[:5]],
                            "elapsedMs": report["elapsedMs"],
                        }
                    ),
                    flush=True,
                )
        report_file = output / (
            "prepared-profiles.json" if args.prepare_only else "comparison.json"
        )
        report_file.write_text(
            json.dumps(
                {
                    "observedAt": datetime.now(UTC).isoformat(),
                    "mode": "read-only retrieval comparison",
                    "scope": "Curated traversal-strategy documents within the configured corpus; other synthetic examples are excluded consistently across profiles.",
                    "profiles": reports,
                    "limitations": [
                        "Retrieved rules are candidates, not proof that adjudication executed them.",
                        "No claim outcomes or policies are changed.",
                        "Vector search prefilters purpose and effective dates; these single-run timings are not a production-scale benchmark.",
                        "Entry-point flags are reported rather than required so the Member OOP accumulator rule can be discovered.",
                    ],
                },
                indent=2,
            )
        )
    finally:
        repo.close()


if __name__ == "__main__":
    main()
