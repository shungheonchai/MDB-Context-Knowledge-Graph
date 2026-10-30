"""Pricing explanations are grounded in recorded outcomes or explicitly bounded reconstruction."""

import re
from decimal import ROUND_HALF_UP, Decimal

from .models import Finding


def explain(claim, member, drug, plan, pa, artifacts):
    c = claim["raw"]
    adjud = c.get("adjudication", {})
    ids = [claim["evidence"].id]
    for result in [member, drug, plan, pa]:
        ids.extend(result["finding"].evidence_ids)
    ids.extend(a["evidence"].id for a in artifacts)
    ids = list(dict.fromkeys(ids))
    missing = [m for result in [member, drug, plan] for m in result["finding"].missing]
    details = {
        "member_paid_cents": adjud.get("memberPaidCents"),
        "allowed_amount_cents": adjud.get("allowedAmountCents"),
        "plan_paid_cents": adjud.get("planPaidCents"),
        "currency": adjud.get("currency", "USD"),
        "components": adjud.get("components", {}),
        "is_generic": drug["finding"].details.get("is_generic"),
        "plan_ref": plan["finding"].resolved_ref,
        "plan_version": plan["finding"].details.get("plan_version"),
        "pa_status": pa["finding"].details.get("pa_status"),
        "pa_changes_cost_sharing": pa["finding"].details.get("changes_cost_sharing"),
        "calculation_steps": [],
        "conflicts": [],
    }
    amount = details["member_paid_cents"]
    components = details["components"]
    if components and all(isinstance(v, int) for v in components.values()):
        if sum(components.values()) != amount:
            details["conflicts"].append(
                "Recorded cost-sharing components do not sum to member payment"
            )
    if isinstance(details["allowed_amount_cents"], int) and isinstance(
        details["plan_paid_cents"], int
    ):
        if details["allowed_amount_cents"] != amount + details["plan_paid_cents"]:
            details["conflicts"].append(
                "Member and plan payments do not reconcile to allowed amount"
            )
    selected = []
    for artifact in artifacts:
        for event in artifact["raw"].get("events", []):
            if event.get("type") == "rule-applied":
                recorded_amount = event.get(
                    "memberCostCents", event.get("outcome", {}).get("memberCostCents")
                )
                if recorded_amount is not None and recorded_amount != amount:
                    details["conflicts"].append(
                        "Source decision amount conflicts with claim amount"
                    )
                elif recorded_amount is not None:
                    selected.append(event)
            if event.get("type") == "price-resolved":
                details["calculation_steps"].append(event)
    status = "insufficient"
    if missing or details["conflicts"]:
        summary = "The recorded member amount is available, but a supported pricing cause cannot yet be established."
    elif selected:
        event = selected[-1]
        # This is recorded source evidence, not a model-generated explanation trace.
        status = "recorded"
        details["classification"] = event.get(
            "classification",
            event.get("outcome", {}).get("classification", adjud.get("classification")),
        )
        details["rule_id"] = event.get("ruleId", event.get("ruleType", adjud.get("ruleId")))
        details["calculation_steps"].append(event)
        summary = "Recorded synthetic adjudication evidence identifies the applied pricing decision and member payment."
    else:
        p = plan["item"]["raw"]
        matching = [
            r
            for r in p.get("benefit", {}).get("drugRules", [])
            if r.get("drugRef") == drug["finding"].resolved_ref
        ]
        benefit = p.get("benefit", {})
        prescription = c.get("prescription", {})
        applicable = all(
            benefit.get(k) in (None, prescription.get(k)) for k in ["channel", "daysSupply"]
        )
        if len(matching) == 1 and applicable and matching[0].get("memberCostCents") == amount:
            status = "reconstructed"
            details["classification"] = matching[0].get("classification")
            details["rule_id"] = matching[0].get("ruleId")
            summary = "Applicable plan configuration supports the recorded amount; actual adjudication rule selection is not recorded."
            missing.append("recorded-rule-selection")
        else:
            exceptions = [
                r
                for r in benefit.get("exceptions", [])
                if r.get("drugRef") == drug["finding"].resolved_ref
            ]
            exception = exceptions[0] if len(exceptions) == 1 else {}
            quantity = prescription.get("quantity")
            supported = False
            if exception.get("type") == "flat-copay":
                copay = exception.get("copayCents")
                allowed = details.get("allowed_amount_cents")
                expected = (
                    min(copay, allowed)
                    if isinstance(copay, int) and isinstance(allowed, int)
                    else copay
                )
                supported = expected == amount and components.get("copayCents") == amount
            elif exception.get("type") == "unit-price":
                unit = exception.get("unitPriceCents")
                allowed = details.get("allowed_amount_cents")
                if (
                    isinstance(unit, int)
                    and isinstance(quantity, int)
                    and unit * quantity == allowed
                ):
                    supported = amount == allowed and components.get("deductibleCents") == amount
                    details["calculation_steps"].append(
                        {
                            "type": "price-reconstructed",
                            "unitPriceCents": unit,
                            "quantity": quantity,
                            "allowedAmountCents": allowed,
                            "exceptionId": exception.get("exceptionId"),
                        }
                    )
            if supported and applicable:
                status = "reconstructed"
                details["rule_id"] = exception.get("exceptionId")
                summary = "The matching plan exception and recorded cost-sharing components support this reconstruction; original rule-selection evidence is missing."
                missing.append("recorded-rule-selection")
            else:
                summary = "Recorded payment is confirmed, but available evidence does not establish a matching pricing calculation."
                missing.append("supported-pricing-calculation")
    if selected and plan["item"] and isinstance(details.get("allowed_amount_cents"), int):
        rule = plan["item"]["raw"].get("benefit", {}).get("defaultCostShare", {})
        event = selected[-1]
        if event.get("ruleType") == rule.get("model") == "deductible-then-coinsurance":
            basis = max(0, details["allowed_amount_cents"] - components.get("deductibleCents", 0))
            bps = rule.get("coinsuranceBps")
            if isinstance(bps, int) and basis:
                percent_amount = int(
                    (Decimal(basis) * Decimal(bps) / 10000).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                minimum = rule.get("coinsuranceMinCents", 0)
                maximum = rule.get("coinsuranceMaxCents")
                configured = max(minimum, percent_amount)
                if isinstance(maximum, int):
                    configured = min(maximum, configured)
                oop_before = event.get("accumulatorsBefore", {}).get("oopRemainingCents")
                if isinstance(oop_before, int):
                    configured = min(
                        configured, max(0, oop_before - components.get("deductibleCents", 0))
                    )
                details["coinsurance_calculation"] = {
                    "basis_cents": basis,
                    "rate_bps": bps,
                    "percentage_amount_cents": percent_amount,
                    "minimum_cents": minimum,
                    "maximum_cents": maximum,
                    "after_constraints_cents": configured,
                    "matches_recorded_component": configured == components.get("coinsuranceCents"),
                }
    details["missing_identity_or_plan"] = bool(
        [m for m in missing if m != "recorded-rule-selection"]
    )
    return Finding(
        claim_id=c["_id"],
        domain="claim",
        status=status,
        summary=summary,
        evidence_ids=ids,
        resolved_ref=c["_id"],
        details=details,
        missing=missing,
    )


def render_answer(question, findings, check_reported_amounts=True):
    if not findings:
        return "Please select a prescription scenario or provide a claim reference so I can check the right records."
    parts = []
    reported = [int(Decimal(x) * 100) for x in re.findall(r"\$(\d+(?:\.\d{1,2})?)", question)]
    recorded = [f.details.get("member_paid_cents") for f in findings]
    supported = {v for v in recorded if isinstance(v, int)}
    if len(recorded) == 2 and all(isinstance(v, int) for v in recorded):
        supported.add(abs(recorded[0] - recorded[1]))
    if check_reported_amounts and reported and any(value not in supported for value in reported):
        mentioned = ", ".join(f"${x / 100:.2f}" for x in dict.fromkeys(reported))
        actual = ", ".join(f"${x / 100:.2f}" for x in recorded if isinstance(x, int))
        parts.append(
            f"Your question mentions {mentioned}, but the selected prescription records show {actual}. I'll explain the recorded amounts below."
        )
    for f in findings:
        d = f.details
        cents = d.get("member_paid_cents")
        amount = f"${cents / 100:.2f}" if isinstance(cents, int) else "unknown"
        lines = [
            f"### {f.claim_id}",
            f"Recorded member payment: **{amount}** ({d.get('currency', 'USD')}).",
            f.summary,
            f"Evidence status: **{f.status}**.",
        ]
        if f.status != "insufficient":
            lines.append(
                f"Applicable plan: `{d.get('plan_ref')}`, version `{d.get('plan_version')}`."
            )
            if d.get("classification"):
                lines.append(
                    f"Benefit classification: **{d['classification']}**; generic product status: **{d.get('is_generic')}**."
                )
            if d.get("rule_id"):
                lines.append(f"Pricing decision/rule: `{d['rule_id']}`.")
        if d.get("components"):
            lines.append(
                "Recorded member components: "
                + "; ".join(
                    f"{k}: ${v / 100:.2f}" for k, v in d["components"].items() if isinstance(v, int)
                )
                + "."
            )
        for step in d.get("calculation_steps", []):
            if step.get("type") in {"price-resolved", "price-reconstructed"}:
                unit, quantity, allowed = (
                    step.get("unitPriceCents"),
                    step.get("quantity"),
                    step.get("allowedAmountCents"),
                )
                if (
                    isinstance(unit, int)
                    and isinstance(quantity, (int, float))
                    and isinstance(allowed, int)
                ):
                    lines.append(
                        f"Pricing arithmetic: ${unit / 100:.2f} per unit × {quantity} units = ${allowed / 100:.2f} allowed amount."
                    )
            before, after = step.get("accumulatorsBefore", {}), step.get("accumulatorsAfter", {})
            for key, label in [
                ("deductibleRemainingCents", "Deductible remaining"),
                ("oopRemainingCents", "Out-of-pocket limit remaining"),
            ]:
                if isinstance(before.get(key), int) and isinstance(after.get(key), int):
                    lines.append(
                        f"Recorded {label.lower()}: ${before[key] / 100:.2f} before → ${after[key] / 100:.2f} after this claim."
                    )
        coins = d.get("coinsurance_calculation")
        if coins and coins["matches_recorded_component"]:
            lines.append(
                f"Configured coinsurance: {coins['rate_bps'] / 100:.2f}% of ${coins['basis_cents'] / 100:.2f} = ${coins['percentage_amount_cents'] / 100:.2f} before constraints. Minimum: ${coins['minimum_cents'] / 100:.2f}; after applicable minimum, maximum, and recorded out-of-pocket constraints: ${coins['after_constraints_cents'] / 100:.2f}, matching the claim component."
            )
        if d.get("pa_changes_cost_sharing") is False:
            lines.append("The applicable PA approves coverage without changing cost-sharing.")
        elif d.get("pa_status") == "not-required":
            lines.append("The source explicitly states PA was not required.")
        else:
            lines.append(
                "PA applicability remains unknown; an absent reference is not proof PA was unnecessary."
            )
        if f.missing:
            lines.append("Evidence gaps: " + ", ".join(f.missing) + ".")
        if d.get("conflicts"):
            lines.append("Conflicting evidence: " + "; ".join(d["conflicts"]) + ".")
        lines.append("Sources: " + ", ".join(f"`{e}`" for e in f.evidence_ids) + ".")
        parts.append("\n\n".join(lines))
    if len(findings) == 2:
        a, b = findings
        av, bv = a.details.get("member_paid_cents"), b.details.get("member_paid_cents")
        if isinstance(av, int) and isinstance(bv, int):
            parts.append(
                f"Recorded payment difference ({a.claim_id} minus {b.claim_id}): **${(av - bv) / 100:.2f}**. "
                "The domain findings above establish which factors are supported; a difference alone does not prove its cause."
            )
    return "\n\n".join(parts)
