# Pricing scenarios

Reusable natural-language questions for the synthetic Atlas fixtures in `context_knowledge_graph_demo`.

These cases test intended behavior. They do not establish that agent execution, retrieval, or pricing calculations have passed end-to-end validation. All business rules and identities are synthetic.

## Data snapshot and revised design

Updated against Atlas on **2026-10-28**. The database contains **61 claims, 10 members, 5 drugs, 6 plan-version records, and 2 prior authorizations**. Domain-context documents mirror all 61 claims, 10 members, 5 drugs, 6 plan versions, and 2 PAs at the root, with additional context fields. Missing source identifiers remain missing; context creation does not invent relationships.

[The data guide](data-guide.md) is the complete inventory: every claim ID, recorded amounts, raw domain references, source-evidence availability, additional member storylines, and the proposed memory-led architecture.

The target design uses private semantic/procedural agent memory, a shared runtime context cache, selective source refresh based on freshness needs, and relevant versioned policies. The current application remains a fixed workflow with domain-handler methods, source checks on reads, and an optional memory adapter. Age-based cache reuse, autonomous tool selection, mainframe commands, and warehouse exports are proposed, not implemented by these fixtures.

**P01–P16** remain the curated UI cases. **S01–S10** below document additional data-backed tests without claiming their runtime support or full evaluation has passed. **M01–M10** in the guide describe design demonstrations that still require new fixtures or behavior.

## How to run

These cases exercise the legacy agent explorer at `/legacy`, not the main Studio's candidate-rule retrieval. Complete the [project setup](../README.md#start-here) first.

1. Start a fresh session for each case, or use a documented reset so previous answers do not supply missing evidence.
2. Select the matching scenario in the demo, then submit or edit its question. The scenario supplies claim references in the background.
3. Record the response, evidence references, result, and any unexpected behavior in the run log.
4. Repeat against the same source versions when comparing changes to models, prompts, or tools.

The backend automatically applies the following requirements to every question; users do not need to type them:

> Explain the recorded member payment, applicable rules, and any missing evidence. Cite exact source records and applicable rule versions. Distinguish recorded facts from reconstructed explanations, and state what cannot be confirmed.

Evaluate observable findings and supporting evidence, rather than exact answer wording. The checks below are evaluator guidance and should not be included in the agent prompt.

## Core claim scenarios

### P01 — Explain the current price

**Claim:** `demo-claim-current`

**Question:**

> Why did I have to pay $75 for this prescription?

**Checks:** Confirm the recorded $75 amount; identify plan v2 and its premium classification and applicable rule. Do not infer the lowest copay from generic status.

### P02 — Compare two fills

**Claims:** `demo-claim-current`, `demo-claim-prior`

**Question:**

> Why is my copay $75 this time when I only paid $25 for the same medicine last time?

**Checks:** Compare the service dates, exact plan versions, and standard versus premium rules. Explain the $50 difference using evidence rather than simply observing that the amounts differ.

### P03 — Distinguish generic status from benefit classification

**Claim:** `demo-claim-current`

**Question:**

> I thought generics were cheaper. Why is my generic medicine being treated as a premium drug?

**Checks:** Separate product-level generic status from plan-specific benefit classification; cite both drug and plan evidence.

### P04 — Explain PA versus pricing

**Claim:** `demo-claim-pa`

**Question:**

> My prior authorization was approved. Why do I still have to pay $75?

**Checks:** Retrieve the applicable PA decision and supporting note. Establish that this synthetic approval covers coverage only and does not change cost-sharing. Link the amount to plan evidence.

### P05 — Resolve a missing drug reference

**Claim:** `demo-claim-missing-drug`

**Question:**

> My receipt shows a $75 charge, but I'm not sure which medicine it's for. Can you check?

**Checks:** Resolve using product code plus code system. Report the method and evidence; distinguish reconstructed pricing applicability from recorded rule selection. Leave the operational claim unchanged.

### P06 — Resolve a missing plan reference

**Claim:** `demo-claim-missing-plan`

**Question:**

> My insurance plan isn't showing on this claim. Can you check which plan covered it and why I paid $75?

**Checks:** Resolve through member coverage and service date. Verify the applicable plan interval rather than choosing the current plan automatically. Label the explanation reconstructed where appropriate.

### P07 — Resolve a missing member reference

**Claim:** `demo-claim-missing-member`

**Question:**

> Can you find this prescription under my account and explain the $75 charge?

**Checks:** Use the composite source-system, subscriber, person-code, and client identifiers. Do not match solely by display name. Retain evidence for the resolved relationship.

### P08 — Resolve multiple missing references

**Claim:** `demo-claim-missing-all-refs`

**Question:**

> I don't have my member or plan details handy. Can you work out why I paid $75 for this prescription?

**Checks:** Resolve member and drug through alternate identifiers, then plan through coverage and service date. Preserve the distinction between matching configuration and recorded adjudication rule selection.

### P09 — Explain a claim without PA

**Claim:** `demo-claim-no-pa`

**Question:**

> Did I need approval before filling this prescription, and why did I pay $75?

**Checks:** Use the explicit synthetic not-required status. Do not treat an absent PA reference alone as proof that authorization was unnecessary.

### P10 — Recognize insufficient identity evidence

**Claim:** `demo-claim-unresolved-identity`

**Question:**

> There's a $75 prescription charge I don't recognize. Can you tell me what it's for?

**Checks:** Confirm the recorded $75 amount but do not invent member, drug, or plan matches from ambiguous names. Request identifying information, report PA status as unknown, and avoid claiming a proven pricing cause.

## Additional pricing-generator scenarios

These curated questions target the original generator cases; the expanded generator now includes cases through 0052. Validate detailed amounts and calculations against the current records and isolated evaluation fixtures; claim names are not evidence.

### P11 — Deductible allocation

**Claim:** `gen-claim-0001-ded-full-absorb`

**Question:**

> Did everything I paid for this prescription go toward my deductible? How much of my deductible is left?

**Checks:** Reconcile allowed amount, member payment, deductible component, and recorded before/after accumulator values. Do not substitute today's member accumulator for the historical claim state.

### P12 — Unit-price exception

**Claim:** `gen-claim-0002-price-exception-unit`

**Question:**

> Was a special price applied to this prescription? Can you show the price per pill and how it added up to $90?

**Checks:** Resolve the missing drug reference, identify the applicable exception, distinguish default from applied unit price, and verify multiplication and currency units.

### P13 — Coinsurance after deductible

**Claim:** `gen-claim-0003-coins-after-ded-met`

**Question:**

> I've met my deductible. Why am I still paying part of the cost of this prescription?

**Checks:** Verify deductible status and the applicable coinsurance rate, minimum, maximum, and any relevant out-of-pocket constraint. Reconcile the explanation to the recorded amount.

### P14 — Out-of-pocket maximum

**Claims:** `gen-claim-0006-oop-max-reached`, `gen-claim-0007-oop-exhausted`

**Question:**

> Why did I pay $90 for one fill and nothing for the next? Did I reach my out-of-pocket limit?

**Checks:** Use claim-specific chronology and accumulator evidence. Explain any cap on the first payment and the subsequent treatment after exhaustion; avoid assuming identical allowed amounts.

### P15 — Benefit change across plan versions

**Claims:** `gen-claim-0008-plan-shift-flat-to-ded`, `gen-claim-0009-plan-shift-deductible`

**Question:**

> Why did the same medicine go from $25 to $120? Did something change in my plan?

**Checks:** Resolve the first claim's missing plan reference, compare effective plan versions and cost-sharing models, and consider other recorded pricing inputs before attributing the entire difference to plan change.

### P16 — Coinsurance minimum

**Claim:** `gen-claim-0013-coins-min-floor`

**Question:**

> My share was supposed to be 20%. Why did I end up paying $5 for this prescription?

**Checks:** Compare percentage-based cost-sharing with the configured minimum, account for other applicable constraints, and reconcile to recorded adjudication components.

## Supplemental scenarios for the expanded dataset

These are evaluator/developer test suggestions backed by records in the October 27 snapshot. They are not additional curated `P` entries or newly passed tests. Select an individual fallback scenario in the UI, or include the listed claim IDs explicitly for a comparison. Use the exact full IDs from the guide’s Appendix when a numeric range is shown.

| Case | Human question | Claim references | Evidence checks |
|---|---|---|---|
| S01 — Price exception and member impact | “If my plan negotiated a lower price, why didn't what I paid go down?” | `gen-claim-0004-price-exception-no-member-impact`; generated 0018, 0030, 0049 | Separate allowed-price calculations from coinsurance caps and the recorded member share. |
| S02 — Generic versus brand copay | “Why is this generic $10 but the brand medicine $40 under the same plan?” | Generated 0010/0011 or 0040/0041 | Compare exact product-specific flat-copay exceptions, not generic labels alone. |
| S03 — Copay below the configured amount | “I expected a $10 copay. Why did I only pay $6?” | `gen-claim-0014-flat-copay-below-allowed`, `gen-claim-0044-member-g-copay-cap` | Check the allowed amount and recorded copay; establish why the configured copay was capped. |
| S04 — Multiple missing references | “I don't have all my insurance details. Can you find this prescription and explain the charge?” | Generated 0015, 0023–0026, 0038–0039, 0045–0048 | Resolve only unique composite member/product matches and date-applicable coverage. Identify missing historical accumulator or rule-selection evidence. |
| S05 — Insufficient identity | “Can you tell me which prescription this charge belongs to?” | `gen-claim-0022-missing-all-refs` | Do not resolve using a similar name or infer a plan; return confirmed facts and request missing identifiers. |
| S06 — Member D progression | “How did my deductible and out-of-pocket limit change what I paid across these fills?” | Generated 0016–0021 | Use claim-specific chronology and recorded accumulator transitions; verify the zero balance and zero payment where supported. |
| S07 — Member E residual balance | “Have I reached my out-of-pocket limit yet, or do I still have some left?” | Generated 0027–0033 | The last record shows a $12 member payment and $13 remaining OOP balance. Do not accept the `oop-exhausted` label as proof of exhaustion. |
| S08 — Member F plan and channel | “Why did I pay $25 before, but much more after my plan changed? Does a mail fill change the explanation?” | Generated 0034–0039 | Compare service-date plan versions, quantity, channel, and missing references; do not attribute quantity changes solely to plan changes. |
| S09 — Member G benefit rules | “Why do some medicines have a fixed copay while others charge me a percentage?” | Generated 0040–0045 | Compare plan exceptions, the default coinsurance model, the $5 minimum, and the $6 allowed-amount cap. |
| S10 — Member H partial identity and balance | “Can you find my missing insurance details and tell me whether I've reached my limit?” | Generated 0046–0052 | Verify composite identity, historical inputs, and actual balances. The last record has a $12 member payment and $6 remaining OOP balance. |

The same medicine can have different quantities or effective prices on repeat fills. Several generated dates extend into November 2026; treat them as synthetic service-date scenarios, not real future transactions.

## Memory and cache demonstrations to add next

The guide’s M01–M10 cases cover stable semantic recall, warm Plan cache reuse, stale Member refresh, early invalidation, conflicting memory, cross-domain reuse, source failure, temporary relocation notes, authorized source updates, and warehouse publication. These do not yet have a complete seeded/demo execution path. In particular, a 90-day Plan budget and a 2-day Member budget are illustrative proposals, not the current backend’s freshness configuration.

## Evaluation and data boundaries

- Operational collections: `claims`, `members`, `drugs`, `plans`, `prior_authorizations`.
- Shared context: `claims_context`, `members_context`, `drugs_context`, `plans_context`, `prior_authorizations_context`, and `rules_policies`.
- Synthetic source artifacts exist in `context_knowledge_graph_archive.decision_traces`, embedded claim context, and the generator-recreated `context_knowledge_graph_demo.decision_traces`. They represent source evidence, not a new target collection for agent reasoning.
- Expected answers exist in both `context_knowledge_graph_eval.expected_answers` and the generator-recreated `context_knowledge_graph_demo.expected_answers`. Both are evaluator-only. Exclude these collections and this catalog’s checks from agent retrieval.
- Operational `decisionTraceRef` values remain unchanged. Resolve the exact artifact and version actually used; do not assume every source artifact exists only in the archive.
- Initial context investigations were marked `not_started`, with explanations `not_generated`. Later runs may enrich context; record that state when comparing runs.
- A source-linked policy reference does not prove that a rule was selected during adjudication. Use recorded decision evidence where available.
- Store any authorized enrichments in context; testing must not modify operational records.

## Repeat-run log

Use one row per test execution. Evidence completeness is part of the result.

| Run / date | Case ID | Model / workflow version | Session / context baseline | Pass / Partial / Fail | Evidence references | Notes / issue |
|---|---|---|---|---|---|---|
| | P01 | | | | | |

A pass requires supported findings, applicable source versions, correct arithmetic where relevant, and appropriate acknowledgment of missing evidence. A deliberate inability to explain P10 is the expected successful behavior.
