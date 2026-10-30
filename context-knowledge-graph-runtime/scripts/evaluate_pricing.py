"""Read-only Atlas integration check for the committed P01–P16 question catalog."""

import asyncio
import json
from dataclasses import replace

from context_knowledge_graph.config import ROOT, Settings
from context_knowledge_graph.events import Execution
from context_knowledge_graph.memory import OptionalMemory
from context_knowledge_graph.models import Principal
from context_knowledge_graph.repository import Repository, digest
from context_knowledge_graph.scenarios import SCENARIOS
from context_knowledge_graph.workflow import build_workflow


async def main():
    settings = replace(
        Settings(),
        use_llm=False,
        enable_context_writes=False,
        memory_url="",
        memory_project="",
        memory_token="",
    )
    repo = Repository(settings)
    try:
        originals = {
            name: list(repo.db[name].find({"provenance.synthetic": True}))
            for name in ["claims", "members", "drugs", "plans", "prior_authorizations"]
        }
        results = []
        for scenario in SCENARIOS:
            case_id = scenario["id"]
            question = scenario["question"]
            execution = Execution(
                case_id,
                "read-only-suite",
                Principal(user_id="evaluator", client_id="synthetic-demo"),
            )
            result = await build_workflow(repo, OptionalMemory(settings), execution).ainvoke(
                {"question": question, "scenario_id": case_id}
            )
            findings = result["findings"]
            row = {
                "case_id": case_id,
                "claims": [f["claim_id"] for f in findings],
                "statuses": [f["status"] for f in findings],
                "amounts_cents": [f["details"]["member_paid_cents"] for f in findings],
                "conflicts": [f["details"]["conflicts"] for f in findings],
                "passed": bool(findings),
            }
            if case_id == "P10":
                row["passed"] = len(findings) == 1 and findings[0]["status"] == "insufficient"
            else:
                row["passed"] = bool(findings) and all(
                    f["status"] in {"recorded", "reconstructed"} for f in findings
                )
            assert not any(
                e["kind"] == "context_write" and e["status"] == "completed"
                for e in execution.events
            )
            results.append(row)
            print(json.dumps(row), flush=True)
        for name, rows in originals.items():
            for row in rows:
                assert digest(repo.db[name].find_one({"_id": row["_id"]})) == digest(row), (
                    "Operational record changed: " + str(row["_id"])
                )
        report = {
            "mode": "read-only evidence tools",
            "cases": results,
            "passed": sum(x["passed"] for x in results),
            "operational_records_unchanged": True,
            "model_calls": 0,
        }
        (ROOT / "data").mkdir(exist_ok=True)
        (ROOT / "data/pricing-smoke-results.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != "cases"}), flush=True)
        if report["passed"] != len(results):
            raise SystemExit(1)
    finally:
        repo.close()


if __name__ == "__main__":
    asyncio.run(main())
