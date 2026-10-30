from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import ROLE_DESCRIPTIONS, Agents
from .models import now
from .pricing import explain, render_answer


class InvestigationState(TypedDict, total=False):
    question: str
    scenario_id: str | None
    instructions: str
    claim_ids: list[str]
    claims: list[Any]
    members: dict
    drugs: dict
    plans: dict
    authorizations: dict
    findings: list[dict]
    answer: str


def build_workflow(repo, memory, execution, llm=None):
    agents = Agents(repo, memory, execution, llm)

    async def synthesize(state):
        execution.event("agent", "claim", status="running", stage="synthesis")
        findings = []
        for claim in state["claims"]:
            claim_id = claim["raw"]["_id"]
            artifacts = await repo.decision_evidence(execution, claim)
            finding = explain(
                claim,
                state["members"][claim_id],
                state["drugs"][claim_id],
                state["plans"][claim_id],
                state["authorizations"][claim_id],
                artifacts,
            )
            finding = await agents.interpret("claim", finding)
            # Incomplete identity cases retain explicit unresolved relationships.
            relationships = {}
            for key, collection in [
                ("member", "members"),
                ("drug", "drugs"),
                ("plan", "plans"),
                ("priorAuthorization", "authorizations"),
            ]:
                resolved = state[collection][claim_id]["finding"]
                if resolved.resolved_ref:
                    relationships[key] = {
                        "ref": resolved.resolved_ref,
                        "method": resolved.details.get("resolution_method", "source-reference"),
                        "verificationStatus": "verified-for-investigation",
                        "evidenceRefs": resolved.evidence_ids,
                        "observedAt": now(),
                    }
            answer = render_answer(state["question"], [finding], check_reported_amounts=False)
            await repo.write(
                execution,
                "claim",
                "claim",
                claim_id,
                finding,
                relationships=relationships,
                explanation={
                    "status": "partial" if finding.status == "insufficient" else "generated",
                    "summary": answer,
                    "evidenceStatus": finding.status,
                    "evidenceRefs": finding.evidence_ids,
                    "generatedAt": now(),
                    "generatedBy": {"agent": "claim", "runId": execution.run_id},
                },
            )
            findings.append(finding)
        answer = render_answer(state["question"], findings)
        execution.event("agent", "claim", status="completed", stage="synthesis")
        execution.event("agent", "coordinator", status="completed", stage="presentation")
        return {"answer": answer, "findings": [f.model_dump() for f in findings]}

    builder = StateGraph(InvestigationState)
    builder.add_node("coordinator", agents.coordinator)
    builder.add_node("claim", agents.claim)
    builder.add_node("member", agents.member)
    builder.add_node("gather_domain_evidence", agents.gather_domain_evidence)
    builder.add_node("synthesis", synthesize)
    builder.add_edge(START, "coordinator")
    builder.add_edge("coordinator", "claim")
    builder.add_edge("claim", "member")
    builder.add_edge("member", "gather_domain_evidence")
    builder.add_edge("gather_domain_evidence", "synthesis")
    builder.add_edge("synthesis", END)
    return builder.compile()


AGENT_CATALOG = [
    {"id": key, "name": key.title() + " Agent", "description": text}
    for key, text in ROLE_DESCRIPTIONS.items()
]
