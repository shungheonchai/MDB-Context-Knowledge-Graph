from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DOMAINS = {
    "claim": ("claims", "claims_context", "claimRef"),
    "member": ("members", "members_context", "memberRef"),
    "drug": ("drugs", "drugs_context", "drugRef"),
    "plan": ("plans", "plans_context", "planRef"),
    "pa": ("prior_authorizations", "prior_authorizations_context", "priorAuthorizationRef"),
}
AGENTS = ["coordinator", "claim", "member", "drug", "plan", "pa"]


def now() -> str:
    return datetime.now(UTC).isoformat()


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    scenario_id: str | None = Field(default=None, max_length=150)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,100}$")


class Principal(BaseModel):
    # Supplied by the server, never trusted from the request body.
    user_id: str
    client_id: str


class Evidence(BaseModel):
    id: str
    domain: str
    collection: str
    database: str | None = None
    document_id: str
    source_version: int | str | None = None
    content_hash: str
    field_paths: list[str] = Field(default_factory=list)
    observed_at: str
    content: dict[str, Any]


class Finding(BaseModel):
    claim_id: str
    domain: str
    status: Literal["recorded", "reconstructed", "insufficient", "not_applicable"]
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_ref: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
