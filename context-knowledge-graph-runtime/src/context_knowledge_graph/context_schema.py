"""Raw-shaped domain context: source fields at root, context enrichments alongside."""

from copy import deepcopy

from .models import now

CONTEXT_SCHEMA_VERSION = 2
RESERVED = {
    "source",
    "freshness",
    "resolvedRelationships",
    "investigation",
    "explanation",
    "revision",
    "contextSchemaVersion",
    "operationalSnapshot",
}


def validate_source(raw, ref_field):
    collisions = RESERVED.intersection(raw)
    if ref_field in raw and raw[ref_field] != raw["_id"]:
        collisions.add(ref_field)
    if collisions:
        raise ValueError("Source/context field collision: " + ", ".join(sorted(collisions)))


def source_metadata(raw, collection, database, content_hash, previous=None):
    result = deepcopy(previous or {})
    result.update(
        database=database,
        collection=collection,
        documentId=raw["_id"],
        contentHash=content_hash,
        sourceVersion=raw.get("version"),
        observedAt=now(),
        provenance=deepcopy(raw.get("provenance", {})),
        fieldNames=sorted(raw),
    )
    return result


def source_projection(cached, raw):
    """None means incomplete; extra context fields never affect the source-content comparison."""
    if cached is None or any(k not in cached for k in raw):
        return None
    return {k: deepcopy(cached[k]) for k in raw}


def mirror_document(raw, previous, collection, database, ref_field, content_hash):
    validate_source(raw, ref_field)
    previous = previous or {}
    prior_fields = set(previous.get("source", {}).get("fieldNames", []))
    if "operationalSnapshot" in previous:
        prior_fields.update(previous["operationalSnapshot"])
        prior_fields.update({"_id", "provenance", "context", "schemaVersion"})
    additions = {
        k: deepcopy(v)
        for k, v in previous.items()
        if k not in prior_fields | {"_id", "operationalSnapshot"}
    }
    if "metadata" in raw and "metadata" in additions:
        # Never silently overwrite source metadata with an existing enrichment.
        if additions["metadata"] != raw["metadata"]:
            raise ValueError("Source metadata conflicts with existing enrichment metadata")
    result = additions | deepcopy(raw)
    result["_id"] = raw["_id"]
    result[ref_field] = raw["_id"]
    result["contextSchemaVersion"] = CONTEXT_SCHEMA_VERSION
    result["source"] = source_metadata(
        raw, collection, database, content_hash, previous.get("source")
    )
    if previous and previous["_id"] != raw["_id"]:
        result["source"]["legacyContextDocumentId"] = previous["_id"]
    result["revision"] = previous.get("revision", 0) + 1
    result.setdefault("resolvedRelationships", {})
    result.setdefault(
        "investigation",
        {
            "status": "not_started",
            "findings": [],
            "hasSignificantFindings": False,
            "missingEvidence": [],
        },
    )
    result.setdefault(
        "explanation", {"status": "not_generated", "summary": None, "evidenceRefs": []}
    )
    result.setdefault("freshness", {})
    result["freshness"].update(
        sourceCheckedAt=now(),
        status="source-mirrored",
        enrichmentsStatus="not-revalidated-by-migration",
    )
    return result


def rewrite_references(value, replacements):
    """Rewrite only known context locations; caller leaves source/user metadata untouched."""
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [rewrite_references(x, replacements) for x in value]
    if isinstance(value, dict):
        return {
            rewrite_references(k, replacements): rewrite_references(v, replacements)
            for k, v in value.items()
        }
    return deepcopy(value)
