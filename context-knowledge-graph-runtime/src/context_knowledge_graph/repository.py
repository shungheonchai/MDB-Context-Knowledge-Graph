import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from .context_schema import (
    CONTEXT_SCHEMA_VERSION,
    source_metadata,
    source_projection,
    validate_source,
)
from .models import DOMAINS, Evidence, now


def plain(value):
    """Stable JSON-safe representation used for source provenance and HTTP responses."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).isoformat()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.loads(json_util.dumps(value))


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True).encode()).hexdigest()


class Repository:
    """Allowlisted reads and compare-and-swap context writes; no operational write API."""

    def __init__(self, settings, database=None):
        self.settings = settings
        self.client = None
        if database is not None:
            self.db = database
        else:
            if not settings.mongo_uri:
                raise RuntimeError("Set CONTEXT_KNOWLEDGE_GRAPH_MONGODB_URI in the local .env")
            # One client per API process, reused by all six agents. Keep driver pool defaults.
            # Fail connection selection within 10s so UI runs can return a useful failure.
            self.client = MongoClient(
                settings.mongo_uri,
                appname="context-knowledge-graph-portable-runtime",
                serverSelectionTimeoutMS=10000,
                tz_aware=True,
            )
            self.db = self.client[settings.database]

    def close(self):
        if self.client is not None:
            self.client.close()

    async def list_claims(self):
        return await asyncio.to_thread(
            lambda: list(
                self.db.claims.find({"provenance.synthetic": True}, {"_id": 1})
                .sort("_id", 1)
                .limit(200)
            )
        )

    async def find(self, domain, query):
        if domain not in DOMAINS:
            raise PermissionError("Unknown operational domain")
        source = DOMAINS[domain][0]
        scoped = {"$and": [query, {"provenance.synthetic": True}]}
        return await asyncio.to_thread(lambda: list(self.db[source].find(scoped).limit(3)))

    async def read(self, execution, agent, domain, object_id):
        if domain not in DOMAINS:
            raise PermissionError("Unknown context domain")
        source, context, ref = DOMAINS[domain]
        execution.event(
            "permission",
            agent,
            status="allowed",
            operation="context_read",
            domain=domain,
            collection=context,
            reason="shared-synthetic-demo-policy",
        )
        execution.event(
            "context_read",
            agent,
            status="running",
            domain=domain,
            collection=context,
            document_id=object_id,
        )
        cached, raw = await asyncio.gather(
            asyncio.to_thread(self.db[context].find_one, {"_id": object_id}),
            asyncio.to_thread(
                self.db[source].find_one, {"_id": object_id, "provenance.synthetic": True}
            ),
        )
        if raw is None:
            execution.event(
                "context_read",
                agent,
                status="missing",
                domain=domain,
                collection=context,
                document_id=object_id,
            )
            return None
        mirrored = source_projection(cached, raw)
        fresh = mirrored is not None and digest(mirrored) == digest(raw)
        facts = mirrored if fresh else raw
        source_fields = [k for k in raw if k != "_id"]
        execution.event(
            "operational_read",
            agent,
            status="completed",
            domain=domain,
            collection=source,
            database=self.db.name,
            document_id=str(raw["_id"]),
            purpose="verify-source-freshness",
        )
        execution.event(
            "context_read",
            agent,
            status="completed",
            domain=domain,
            collection=context,
            document_id=str(raw["_id"]),
            freshness="verified" if fresh else "stale-or-uninitialized",
            reused_context=bool(fresh and cached.get("investigation", {}).get("findings")),
            fields=source_fields,
            context_revision=(cached or {}).get("revision"),
        )
        ev = Evidence(
            id=f"{source}/{raw['_id']}",
            domain=domain,
            collection=source,
            database=self.db.name,
            document_id=str(raw["_id"]),
            source_version=raw.get("version"),
            content_hash=digest(raw),
            observed_at=now(),
            field_paths=source_fields,
            content=plain(facts),
        )
        execution.add_evidence(ev)
        # Only current source facts are returned; cached agent prose is never adjudication proof.
        return {"raw": facts, "context": cached, "evidence": ev}

    async def policies(self, execution, agent, plan_id):
        rows = await asyncio.to_thread(
            lambda: list(
                self.db.rules_policies.find(
                    {"scope.planRef": plan_id, "provenance.synthetic": True}
                ).limit(20)
            )
        )
        for raw in rows:
            execution.add_evidence(
                Evidence(
                    id=f"rules_policies/{raw['_id']}",
                    domain="policy",
                    collection="rules_policies",
                    database=self.db.name,
                    document_id=str(raw["_id"]),
                    source_version=raw.get("version"),
                    content_hash=digest(raw),
                    observed_at=now(),
                    field_paths=["scope", "content", "authority"],
                    content=plain(raw),
                )
            )
        execution.event(
            "context_read",
            agent,
            status="completed",
            domain="policy",
            collection="rules_policies",
            document_id=plan_id,
            count=len(rows),
        )
        return rows

    async def write(
        self, execution, agent, domain, object_id, finding, relationships=None, explanation=None
    ):
        if agent != domain:
            execution.event(
                "permission", agent, status="denied", operation="context_write", domain=domain
            )
            raise PermissionError("An agent can write only its own domain context")
        if not self.settings.enable_context_writes:
            execution.event(
                "context_write",
                agent,
                status="skipped",
                domain=domain,
                reason="context writes disabled",
            )
            return
        await asyncio.to_thread(
            self._write, execution, agent, domain, object_id, finding, relationships, explanation
        )

    def _write(self, execution, agent, domain, object_id, finding, relationships, explanation):
        source, target, ref = DOMAINS[domain]
        raw = self.db[source].find_one({"_id": object_id, "provenance.synthetic": True})
        if raw is None:
            raise PermissionError("Context updates require an authorized synthetic source")
        validate_source(raw, ref)
        evidence = [
            execution.evidence[x].model_dump()
            for x in finding.evidence_ids
            if x in execution.evidence
        ]
        operational_names = {v[0] for v in DOMAINS.values()}
        for ev in evidence:
            if ev["collection"] in operational_names:
                current = self.db[ev["collection"]].find_one(
                    {"_id": ev["document_id"], "provenance.synthetic": True}
                )
                if current is None or digest(current) != ev["content_hash"]:
                    raise RuntimeError(
                        "Source changed during investigation; refresh evidence before writing context"
                    )
        hashes = {e["id"]: e["content_hash"] for e in evidence}
        entry = finding.model_dump() | {
            "evidenceHashes": hashes,
            "contributedBy": agent,
            "runId": execution.run_id,
            "updatedAt": now(),
        }
        for _ in range(3):
            old = self.db[target].find_one({"_id": object_id})
            legacy = self.db[target].find_one({ref: object_id}) if old is None else None
            if legacy is not None:
                raise RuntimeError(
                    "Legacy context identity found; run context-mirror migration first"
                )
            if old and "metadata" in raw and old.get("metadata") not in (None, raw["metadata"]):
                raise ValueError("Source metadata conflicts with existing enrichment metadata")
            revision = (old or {}).get("revision", 0)
            findings = deepcopy((old or {}).get("investigation", {}).get("findings", []))
            previous = next(
                (
                    f
                    for f in findings
                    if f.get("claim_id") == finding.claim_id and f.get("domain") == domain
                ),
                None,
            )
            reinforcement = "new"
            if previous:
                same_conclusion = previous.get("status") == entry["status"] and {
                    k: v
                    for k, v in previous.get("details", {}).items()
                    if k != "agent_interpretation"
                } == {k: v for k, v in entry["details"].items() if k != "agent_interpretation"}
                old_hashes = previous.get("evidenceHashes", {})
                if same_conclusion and old_hashes == hashes:
                    reinforcement = "reused"
                elif (
                    same_conclusion
                    and set(old_hashes) < set(hashes)
                    and all(hashes.get(k) == v for k, v in old_hashes.items())
                ):
                    reinforcement = "corroborated"
                elif not same_conclusion:
                    reinforcement = (
                        "conflicted" if entry["details"].get("conflicts") else "corrected"
                    )
                else:
                    reinforcement = "source_updated"
            entry["reinforcement"] = reinforcement
            findings = [
                f
                for f in findings
                if not (f.get("claim_id") == finding.claim_id and f.get("domain") == domain)
            ]
            # Refuse silent loss of historical per-claim context on shared member/plan objects.
            if len(findings) >= 200:
                raise RuntimeError("Context findings capacity reached; archive before adding more")
            findings.append(entry)
            updates = {
                **{k: deepcopy(v) for k, v in raw.items() if k != "_id"},
                "contextSchemaVersion": CONTEXT_SCHEMA_VERSION,
                "source": source_metadata(
                    raw, source, self.db.name, digest(raw), (old or {}).get("source")
                ),
                "investigation.findings": findings,
                "investigation.status": "partial" if finding.missing else "complete",
                "investigation.hasSignificantFindings": bool(finding.missing),
                "investigation.missingEvidence": finding.missing,
                "freshness": {
                    "assembledAt": now(),
                    "sourceCheckedAt": now(),
                    "dependenciesCheckedAt": now(),
                    "status": "verified-for-investigation",
                },
            }
            if previous and reinforcement in {"corrected", "conflicted", "source_updated"}:
                history = deepcopy((old or {}).get("investigation", {}).get("revisions", []))
                if len(history) >= 100:
                    raise RuntimeError(
                        "Context revision history capacity reached; archive before updating"
                    )
                history.append(previous)
                updates["investigation.revisions"] = history
            if relationships is not None:
                extra = {
                    k: v
                    for k, v in (old or {}).get("resolvedRelationships", {}).items()
                    if k not in {"member", "drug", "plan", "priorAuthorization"}
                }
                updates["resolvedRelationships"] = extra | relationships
            if explanation:
                updates["explanation"] = explanation
            key = (
                {"_id": old["_id"], "revision": revision}
                if old
                else {"_id": object_id, "revision": {"$exists": False}}
            )
            if old and "revision" not in old:
                key["revision"] = {"$exists": False}
            stale_fields = set((old or {}).get("source", {}).get("fieldNames", [])) - set(raw)
            unset_fields = {k: "" for k in stale_fields if k not in {"_id"}}
            unset_fields["operationalSnapshot"] = ""
            try:
                result = self.db[target].update_one(
                    key,
                    {
                        "$set": updates,
                        "$inc": {"revision": 1},
                        "$setOnInsert": {} if ref in updates else {ref: object_id},
                        "$unset": unset_fields,
                    },
                    upsert=old is None,
                )
            except DuplicateKeyError:
                continue
            if not (result.matched_count or result.upserted_id is not None):
                continue
            # Emit on the owning asyncio loop; execution.event is marshaled by the caller.
            execution.event(
                "context_write",
                agent,
                status="completed",
                domain=domain,
                collection=target,
                document_id=object_id,
                revision=revision + 1,
                changes={"before": plain(previous), "after": plain(entry)},
            )
            execution.event(
                "context_reinforcement",
                agent,
                status=reinforcement,
                domain=domain,
                collection=target,
                document_id=object_id,
                evidence_ids=finding.evidence_ids,
                meaning="Repeat access is reuse, not additional independent evidence",
            )
            for ev in evidence:
                execution.event(
                    "context_relationship",
                    agent,
                    status="supported_by",
                    source=f"{target}/{object_id}",
                    target=ev["id"],
                    source_domain=domain,
                    target_domain=ev["domain"],
                    relation="supported_by",
                    evidence_id=ev["id"],
                )
            return
        raise RuntimeError("Concurrent context update conflict; retry the investigation")

    async def decision_evidence(self, execution, claim_item):
        """Read historical fixture artifacts by exact claim linkage; never evaluator answers."""
        claim = claim_item["raw"]
        linked = [
            e["artifact"]
            for e in (claim_item.get("context") or {})
            .get("investigation", {})
            .get("recordedSourceEvidence", [])
            if e.get("artifact")
        ]
        origin_database = self.db.name
        origin_collection = "claims_context"
        origin_id = (claim_item.get("context") or {}).get("_id", claim["_id"])
        if not linked and claim.get("adjudication", {}).get("decisionTraceRef"):
            trace_id = claim["adjudication"]["decisionTraceRef"]
            for database in [self.db, self.db.client["context_knowledge_graph_archive"]]:
                row = await asyncio.to_thread(
                    database.decision_traces.find_one,
                    {"_id": trace_id, "provenance.synthetic": True},
                )
                if row:
                    linked.append(row)
                    origin_database = database.name
                    origin_collection = "decision_traces"
                    origin_id = row["_id"]
                    break
        results = []
        for row in linked:
            if row.get("claimRef", row.get("businessObject", {}).get("id")) != claim["_id"]:
                continue
            ev = Evidence(
                id=f"{origin_database}.{origin_collection}/{origin_id}#source:{row['_id']}",
                domain="claim",
                collection=origin_collection,
                database=origin_database,
                document_id=str(row["_id"]),
                content_hash=digest(row),
                observed_at=now(),
                field_paths=[
                    "investigation.recordedSourceEvidence"
                    if origin_collection == "claims_context"
                    else "events"
                ],
                content=plain(row),
            )
            execution.add_evidence(ev)
            results.append({"raw": row, "evidence": ev})
        execution.event(
            "source_evidence",
            "claim",
            status="completed",
            count=len(results),
            document_id=claim["_id"],
            origin="recorded-synthetic-source",
        )
        return results
