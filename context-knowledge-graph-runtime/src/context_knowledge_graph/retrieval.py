"""Shared, read-only hybrid retrieval profiles used by the CLI and pipeline workbench."""

import json
from datetime import datetime

from bson import ObjectId

from .config import Settings

LEXICAL_INDEX = Settings().lexical_index
VECTOR_INDEX = "autoEmbed_ruleData"
PROFILES = ["balanced_rrf", "terminology_rrf", "context_rrf"]
CASES = [
    {
        "id": "oopm",
        "question": "Why am I still paying coinsurance after reaching my OOPM?",
        "claim_ids": ["gen-claim-0006-oop-max-reached", "gen-claim-0007-oop-exhausted"],
    },
    {"id": "charge25", "question": "Why was I charged $25?", "claim_ids": ["demo-claim-prior"]},
]
# Equivalent terms and related concepts are deliberately separate.
GLOSSARY = [
    {
        "trigger": "oopm",
        "equivalents": ["out-of-pocket maximum", "out of pocket limit"],
        "related": ["family out-of-pocket accumulator", "individual accumulator"],
    },
    {"trigger": "coinsurance", "equivalents": ["co-insurance"], "related": []},
    {"trigger": "copay", "equivalents": ["co-pay", "copayment"], "related": []},
]


def claim_context(claims):
    parts = []
    for claim in claims:
        outcome = claim.get("adjudication", {})
        components = outcome.get("components", {})
        positive = [
            key.removesuffix("Cents")
            for key, value in components.items()
            if isinstance(value, (int, float)) and value > 0
        ]
        parts.append(
            " ".join(
                [
                    f"recorded member payment {outcome.get('memberPaidCents', 0) / 100:.2f} USD",
                    "recorded payment components " + " ".join(positive),
                    "classification " + str(outcome.get("classification", "unknown")),
                    "plan " + str(claim.get("planRef", "unknown")),
                ]
            )
        )
    return "; ".join(parts)


def make_pipeline(case, claims, profile, corpus_size, *, vector_mode="exact", num_candidates=1000):
    service_date = claims[0]["serviceDate"]
    date = (
        datetime.fromisoformat(service_date.replace("Z", "+00:00"))
        if isinstance(service_date, str)
        else service_date
    )
    applicability = {
        "purpose": "traversal-strategy",
        "effStartDate": {"$lte": date},
        "effEndDate": {"$gt": date},
    }
    question = case["question"]
    expansions, related = [], []
    if profile == "terminology_rrf":
        for term in GLOSSARY:
            if term["trigger"] in question.lower():
                expansions.extend(term["equivalents"])
                related.extend(term["related"])
    context = claim_context(claims) if profile == "context_rrf" else ""
    retrieval_text = " ".join([question, *expansions, context]).strip()
    clauses = [{"text": {"query": retrieval_text, "path": "ruleDataText"}}]
    if profile == "terminology_rrf":
        clauses.append(
            {
                "text": {
                    "query": " ".join([question, *expansions, *related]),
                    "path": ["ruleName", "ruleSubType"],
                    "score": {"boost": {"value": 4}},
                }
            }
        )
        # An exact approved concept phrase receives its own lexical preference.
        for phrase in expansions + related:
            clauses.append(
                {"phrase": {"query": phrase, "path": "ruleName", "score": {"boost": {"value": 3}}}}
            )
    elif profile == "context_rrf":
        components = [
            key.removesuffix("Cents")
            for key, value in claims[0].get("adjudication", {}).get("components", {}).items()
            if isinstance(value, (int, float)) and value > 0
        ]
        if components:
            clauses.append(
                {
                    "text": {
                        "query": " ".join(components),
                        "path": ["ruleName", "ruleSubType"],
                        "score": {"boost": {"value": 4}},
                    }
                }
            )
    lexical = [
        {
            "$search": {
                "index": LEXICAL_INDEX,
                "compound": {
                    "filter": [
                        {"equals": {"path": "purpose", "value": "traversal-strategy"}},
                        {"range": {"path": "effStartDate", "lte": date}},
                        {"range": {"path": "effEndDate", "gt": date}},
                    ],
                    "should": clauses,
                    "minimumShouldMatch": 1,
                },
            }
        },
        {"$limit": 50},
    ]
    # Apply the same applicability scope inside both retrieval branches.
    # Exact search is the baseline; ANN is an explicit recall/latency comparison.
    if vector_mode not in {"exact", "ann"}:
        raise ValueError("Choose exact or ann vector search")
    if not 50 <= num_candidates <= 10000:
        raise ValueError("ANN numCandidates must be between 50 and 10000")
    vector_query = {
        "index": VECTOR_INDEX,
        "path": "ruleDataText",
        "query": retrieval_text,
        "filter": applicability,
        "limit": 50,
    }
    if vector_mode == "exact":
        vector_query["exact"] = True
    else:
        vector_query["numCandidates"] = num_candidates
    vector = [{"$vectorSearch": vector_query}]
    pipeline = [
        {
            "$rankFusion": {
                "input": {"pipelines": {"lexical": lexical, "vector": vector}},
                "combination": {"weights": {"lexical": 1, "vector": 1}},
                "scoreDetails": True,
            }
        },
        {"$limit": 8},
        {"$set": {"fusionDetails": {"$meta": "scoreDetails"}}},
        {
            "$graphLookup": {
                "from": "rulesSets",
                "startWith": "$ruleId",
                "connectFromField": "relationships.targetRuleId",
                "connectToField": "ruleId",
                "as": "ruleGraph",
                "maxDepth": 5,
                "depthField": "depth",
                "restrictSearchWithMatch": {
                    "effStartDate": {"$lte": date},
                    "effEndDate": {"$gt": date},
                },
            }
        },
        {
            "$set": {
                "ruleGraph": {
                    "$sortArray": {"input": "$ruleGraph", "sortBy": {"depth": 1, "ruleName": 1}}
                }
            }
        },
        {
            "$project": {
                "ruleId": 1,
                "ruleName": 1,
                "ruleDomain": 1,
                "version": 1,
                "entryPoint": 1,
                "relationships": 1,
                "scoreDetails": "$fusionDetails",
                "graphCount": {"$size": "$ruleGraph"},
                "ruleGraph.ruleId": 1,
                "ruleGraph.ruleName": 1,
                "ruleGraph.ruleDomain": 1,
                "ruleGraph.version": 1,
                "ruleGraph.relationships": 1,
                "ruleGraph.depth": 1,
            }
        },
    ]
    return pipeline, {
        "retrievalText": retrieval_text,
        "equivalentExpansions": expansions,
        "relatedConcepts": related,
        "claimContext": context,
        "lexicalBoosts": [
            {
                "operator": operator,
                "query": options["query"],
                "paths": options["path"]
                if isinstance(options["path"], list)
                else [options["path"]],
                "boost": options["score"]["boost"]["value"],
            }
            for clause in clauses
            for operator, options in clause.items()
            if "score" in options
        ],
        "fillDate": date.isoformat(),
        "lexicalVectorWeights": {"lexical": 1, "vector": 1},
        "vectorMode": vector_mode,
        "vectorLimit": 50,
        "numCandidates": num_candidates if vector_mode == "ann" else None,
    }


def shell(value, indent=0):
    """Readable Compass syntax with real BSON constructors, not literal EJSON objects."""
    if isinstance(value, datetime):
        return f"ISODate({json.dumps(value.isoformat())})"
    if isinstance(value, ObjectId):
        return f"ObjectId({json.dumps(str(value))})"
    pad = " " * indent
    nested = " " * (indent + 2)
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = [
            nested + json.dumps(key) + ": " + shell(item, indent + 2) for key, item in value.items()
        ]
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return (
            "[\n"
            + ",\n".join(nested + shell(item, indent + 2) for item in value)
            + "\n"
            + pad
            + "]"
        )
    return json.dumps(value)
