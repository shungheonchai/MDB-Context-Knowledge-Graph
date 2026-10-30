"""Member-facing questions and background claim selection; never expected answers."""

EVIDENCE_INSTRUCTIONS = (
    "Explain the recorded member payment, applicable rules, and any missing evidence. "
    "Cite exact source records and applicable rule versions. Distinguish recorded facts "
    "from reconstructed explanations, and state what cannot be confirmed. "
    "Do not assume that amounts or premises in the member's question are recorded facts."
)

SCENARIOS = [
    {
        "id": "P01",
        "title": "Understand a $75 copay",
        "claim_ids": ["demo-claim-current"],
        "question": "Why did I have to pay $75 for this prescription?",
    },
    {
        "id": "P02",
        "title": "Same medicine, higher copay",
        "claim_ids": ["demo-claim-current", "demo-claim-prior"],
        "question": "Why is my copay $75 this time when I only paid $25 for the same medicine last time?",
    },
    {
        "id": "P03",
        "title": "A generic treated as premium",
        "claim_ids": ["demo-claim-current"],
        "question": "I thought generics were cheaper. Why is my generic medicine being treated as a premium drug?",
    },
    {
        "id": "P04",
        "title": "Approved, but still paying $75",
        "claim_ids": ["demo-claim-pa"],
        "question": "My prior authorization was approved. Why do I still have to pay $75?",
    },
    {
        "id": "P05",
        "title": "Identify the medicine on a charge",
        "claim_ids": ["demo-claim-missing-drug"],
        "question": "My receipt shows a $75 charge, but I'm not sure which medicine it's for. Can you check?",
    },
    {
        "id": "P06",
        "title": "Find the plan behind a charge",
        "claim_ids": ["demo-claim-missing-plan"],
        "question": "My insurance plan isn't showing on this claim. Can you check which plan covered it and why I paid $75?",
    },
    {
        "id": "P07",
        "title": "Find a prescription under my account",
        "claim_ids": ["demo-claim-missing-member"],
        "question": "Can you find this prescription under my account and explain the $75 charge?",
    },
    {
        "id": "P08",
        "title": "Missing my insurance details",
        "claim_ids": ["demo-claim-missing-all-refs"],
        "question": "I don't have my member or plan details handy. Can you work out why I paid $75 for this prescription?",
    },
    {
        "id": "P09",
        "title": "Was prior approval needed?",
        "claim_ids": ["demo-claim-no-pa"],
        "question": "Did I need approval before filling this prescription, and why did I pay $75?",
    },
    {
        "id": "P10",
        "title": "An unrecognized prescription charge",
        "claim_ids": ["demo-claim-unresolved-identity"],
        "question": "There's a $75 prescription charge I don't recognize. Can you tell me what it's for?",
    },
    {
        "id": "P11",
        "title": "What went toward my deductible?",
        "claim_ids": ["gen-claim-0001-ded-full-absorb"],
        "question": "Did everything I paid for this prescription go toward my deductible? How much of my deductible is left?",
    },
    {
        "id": "P12",
        "title": "How was this prescription priced?",
        "claim_ids": ["gen-claim-0002-price-exception-unit"],
        "question": "Was a special price applied to this prescription? Can you show the price per pill and how it added up to $90?",
    },
    {
        "id": "P13",
        "title": "Still paying after meeting my deductible",
        "claim_ids": ["gen-claim-0003-coins-after-ded-met"],
        "question": "I've met my deductible. Why am I still paying part of the cost of this prescription?",
    },
    {
        "id": "P14",
        "title": "One fill costs $90, the next is free",
        "claim_ids": ["gen-claim-0006-oop-max-reached", "gen-claim-0007-oop-exhausted"],
        "question": "Why did I pay $90 for one fill and nothing for the next? Did I reach my out-of-pocket limit?",
    },
    {
        "id": "P15",
        "title": "My copay went from $25 to $120",
        "claim_ids": [
            "gen-claim-0008-plan-shift-flat-to-ded",
            "gen-claim-0009-plan-shift-deductible",
        ],
        "question": "Why did the same medicine go from $25 to $120? Did something change in my plan?",
    },
    {
        "id": "P16",
        "title": "Why is my percentage share $5?",
        "claim_ids": ["gen-claim-0013-coins-min-floor"],
        "question": "My share was supposed to be 20%. Why did I end up paying $5 for this prescription?",
    },
]


def scenario_by_id(scenario_id):
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)


def available_scenarios(claim_ids):
    """Offer curated questions first, followed by human prompts for other available claims."""
    known = set(claim_ids)
    result = [s for s in SCENARIOS if set(s["claim_ids"]) <= known]
    covered = {cid for s in result for cid in s["claim_ids"]}
    for cid in sorted(known - covered):
        words = cid.removeprefix("gen-claim-").removeprefix("demo-claim-")
        words = words.split("-", 1)[1] if words.split("-", 1)[0].isdigit() else words
        title = words.replace("-", " ").capitalize()
        question = "Can you help me understand what I paid for this prescription and why?"
        for keyword, prompt in [
            ("oop", "Did my out-of-pocket limit change how much I paid for this prescription?"),
            (
                "price-exception",
                "Did my plan give this medicine a special price? Can you show how my total was calculated?",
            ),
            ("coins", "How did my plan work out the share I paid for this medicine?"),
            (
                "ded",
                "How much of this prescription payment went toward my deductible, and how much is left?",
            ),
            (
                "repeat-fill",
                "I'm filling this medicine again. Can you explain what I paid this time?",
            ),
            (
                "missing",
                "Can you find my prescription and insurance details and help me understand this charge?",
            ),
            (
                "flat-copay",
                "Why did I pay this copay for my medicine? Was there a special rule in my plan?",
            ),
        ]:
            if keyword in cid:
                question = prompt
                break
        result.append(
            {
                "id": "claim:" + cid,
                "title": title,
                "claim_ids": [cid],
                "question": question,
            }
        )
    return result


def resolve_scenario(scenario_id):
    if not scenario_id:
        return []
    scenario = scenario_by_id(scenario_id)
    if scenario:
        return list(scenario["claim_ids"])
    if scenario_id.startswith("claim:"):
        return [scenario_id.removeprefix("claim:")]
    raise ValueError("Unknown pricing scenario")
