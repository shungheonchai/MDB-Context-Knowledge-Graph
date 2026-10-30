# Data guide

Context mirrors verified in Atlas on **2026-10-28**. Scenario and auxiliary-collection details were inventoried on October 27. This is a point-in-time inventory, not a live dashboard.

This guide describes all **61 synthetic claims**, their Member/Drug/Plan/PA dependencies, what the fixtures demonstrate, and how they relate to the revised context-layer design. No real member data or healthcare policies are represented. The October 28 migration updated context collections only; operational records were verified unchanged.

For member-facing test questions and evaluator checks, use [the pricing scenarios](pricing-scenarios.md). For the executable demo, see [the project README](../README.md).

The current primary runtime view is the [pipeline workbench](demo-guide.md), demonstrating rule selection, versioned relationships, native reranking, and stage-level query inspection. Agent-handler behavior described below remains available in the legacy explorer at `/legacy`. The new workbench performs read-only retrieval; the memory-assisted continuation is a conceptual handoff.

The later rule-library expansion adds `context_knowledge_graph_demo.rulesSets`: 3,021 rule-version documents, including 31 curated traversal-strategy documents. MAC version 3 is effective October 1 and extends the copay graph; version 2 retains the earlier topology. These library rules are synthetic retrieval fixtures, not proof of the rules that adjudicated the operational claims. See [the rule migration notes](data-guide.md#fixture-maintenance) and [hybrid demo guide](demo-guide.md#cli-comparison-and-compass-export).

## 1. Current data, current runtime, and proposed architecture

These are three different states:

| Area | Verified current state | Proposed direction |
|---|---|---|
| Domain components | Six roles implemented as methods on one `Agents` object, with application-defined routing | Independent decision loops, scoped tools, state, and private memory for each domain agent |
| Memory | Standalone memory SDK adapter exists; this data inventory does not prove a memory service is connected or populated | Consult individual semantic and procedural memory first for established knowledge and investigation procedures |
| Context collections | Shared operational snapshots plus attributed enrichments; current reads also check raw source data | Shared runtime cache that reduces expensive mainframe/tool/MCP reads when evidence is sufficiently fresh |
| Freshness | Current code compares source facts during reads and before context writes | Field/question-aware freshness budgets, selective refresh, and event-driven invalidation |
| Policies | Six versioned references to synthetic plan benefit configuration | Consult relevant healthcare/business rules and policy versions when needed |
| Source writes | Operational records are read-only in the current demo | A domain agent may initiate an allowed command through the owning application/service |
| Warehouse | No warehouse connector or export job | Policy-driven publication of curated business records and outcomes |
| Hosting | One local Docker application; LangGraph/FastAPI/React | Runtime remains application-owned and portable |

Independent agent loops and age-based cache refresh are proposed behavior, not implemented features of the current Studio.

## 2. Collection inventory

Database: `context_knowledge_graph_demo`.

| Operational collection | Records | Context collection | Records | Source records without a context document |
|---|---|---|---|---|
| `claims` | 61 | `claims_context` | 61 | 0 |
| `members` | 10 | `members_context` | 10 | 0 |
| `drugs` | 5 | `drugs_context` | 5 | 0 |
| `plans` | 6 | `plans_context` | 6 | 0 |
| `prior_authorizations` | 2 | `prior_authorizations_context` | 2 | 0 |

| Additional collection | Records | Meaning |
|---|---|---|
| `context_knowledge_graph_demo.rules_policies` | 6 | Synthetic versioned plan-benefit references |
| `context_knowledge_graph_demo.decision_traces` | 52 | Generator-created recorded source artifacts; legacy fixture support |
| `context_knowledge_graph_demo.expected_answers` | 52 | Generator-created evaluator data; exclude from agent access |
| `context_knowledge_graph_archive.decision_traces` | 35 | Earlier archived source artifacts |
| `context_knowledge_graph_eval.expected_answers` | 35 | Earlier isolated evaluator fixtures |

The generator has recreated `decision_traces` and `expected_answers` in the demo database after the earlier migration. Their existence does not reinstate standalone agent-decision traces as the target architecture. Both current and archived copies can overlap; do not add their counts as though they were all distinct cases. The runtime does not query either expected-answer collection. Keep evaluator-only content outside agent retrieval, including this guide’s expected checks.

All 84 operational documents now have context mirrors. The migration reshaped 54 existing context documents and initialized 30 missing ones. Original context documents are backed up in `context_knowledge_graph_archive.context_mirror_backups`. A future missing context document represents a cache miss, not necessarily missing operational data.

Investigation status changes as the legacy demo runs. A new browser session does not clear shared context; record the context baseline for repeatable evaluations.

## 3. Domain records and their roles

### Members — identity and coverage

Member records link to coverage by plan code and effective interval. Several claims deliberately omit a direct member reference but supply a composite source-system/subscriber/person/client identifier. Match those exact identifiers; a name alone is insufficient.

| Member ID | Coverage plan code | Directly linked claims | Exact alternate-identifier candidates | Member context |
|---|---|---|---|---|
| `demo-member-001` | DEMO-PREMIUM-GENERIC | 3 | 0 | Seeded |
| `demo-member-002` | DEMO-PREMIUM-GENERIC | 3 | 2 | Seeded |
| `gen-member-a` | GEN-HDHP | 7 | 0 | Seeded |
| `gen-member-b` | GEN-SHIFT | 2 | 1 | Seeded |
| `gen-member-c` | GEN-FLAT | 6 | 2 | Seeded |
| `gen-member-d` | GEN-HDHP | 6 | 1 | Seeded |
| `gen-member-e` | GEN-HDHP | 7 | 0 | Not seeded at snapshot |
| `gen-member-f` | GEN-SHIFT | 4 | 2 | Not seeded at snapshot |
| `gen-member-g` | GEN-FLAT | 6 | 0 | Not seeded at snapshot |
| `gen-member-h` | GEN-HDHP | 4 | 3 | Not seeded at snapshot |

Alternate-identifier counts are documentation-time matches, not persisted repairs or proof that a runtime investigation has completed. Coverage uses `from`/`thru` in the original demo records and `validFrom`/`validTo` in generated records. Current member balances must not replace historical claim-specific accumulator evidence.

### Drugs — product facts and price history

| Drug ID | Synthetic product | Source classification | Source price history |
|---|---|---|---|
| `demo-drug-001` | Synthetic Generic A | generic | No source unit-price history; use plan fixed-copay fixture |
| `gen-drug-a` | Fixture Generic A | generic | 2026-01-01: $2.00/unit |
| `gen-drug-b` | Fixture Generic B | generic | 2026-01-01: $3.50/unit; 2026-08-01: $4.00/unit |
| `gen-drug-c` | Fixture Brand C | brand | 2026-01-01: $10.00/unit |
| `gen-drug-d` | Fixture Specialty D | specialty | 2026-01-01: $25.00/unit |

Product classification and plan benefit treatment are separate. A generic product can have a premium plan classification. A specialty classification alone does not establish whether a product is generic or brand. Drug price history and plan-specific exceptions can produce different allowed prices.

### Plans — historical versions and embedded rules

All amounts below describe mock configuration, not actual payer or pharmacy benefit policy. `v1`/`v2` values in generated records are strings; the original demo versions are integers. Do not assume uniform source representation.

| Plan document | Plan code | Version | Effective interval, end exclusive | Embedded configuration |
|---|---|---|---|---|
| `demo-plan-v1` | `DEMO-PREMIUM-GENERIC` | 1 | 2026-01-01 to 2026-10-01 | standard: $25.00 for demo-drug-001 |
| `demo-plan-v2` | `DEMO-PREMIUM-GENERIC` | 2 | 2026-10-01 to open-ended | premium: $75.00 for demo-drug-001 |
| `gen-plan-hdhp-v1` | `GEN-HDHP` | v1 | 2026-01-01 to open-ended | deductible $150.00; OOP maximum $500.00; 20% coinsurance; min $5.00; max $100.00; gen-drug-b: unit-price $3.00/unit; gen-drug-d: percent-of-default 80% of default price |
| `gen-plan-flat-v1` | `GEN-FLAT` | v1 | 2026-01-01 to open-ended | 20% coinsurance; min $5.00; max $100.00; gen-drug-a: flat-copay $10.00; gen-drug-c: flat-copay $40.00 |
| `gen-plan-shift-v1` | `GEN-SHIFT` | v1 | 2026-01-01 to 2026-10-01 | gen-drug-b: flat-copay $25.00 |
| `gen-plan-shift-v2` | `GEN-SHIFT` | v2 | 2026-10-01 to open-ended | deductible $150.00; 20% coinsurance; min $5.00; max $100.00 |

A pricing percentage exception changes the source price used for allowed-amount calculation; it is not automatically the member’s coinsurance percentage. A plan named `GEN-FLAT` still contains a default coinsurance model, with flat-copay exceptions for specific products. Apply source configuration, not names.

### Prior authorizations — approval scope

| PA ID | Member | Drug | Interval | Recorded scope |
|---|---|---|---|---|
| `demo-pa-001` | `demo-member-001` | `demo-drug-001` | 2026-10-01 to 2026-11-01 | approved; coverage-only; changesCostSharing=False |
| `gen-pa-coverage-only` | `gen-member-a` | `gen-drug-c` | 2026-10-01 to 2026-11-01 | approved; coverage-only; changesCostSharing=False |

Both PA records demonstrate coverage approval without a cost-sharing exception. A missing `paRef` does not establish no PA, no PA requirement, or a pricing exception. Some claims explicitly record `priorAuthorization.status: "not-required"`; others remain unknown.

### Rules and policies — source-linked reference records

| Policy ID | Referenced plan version | Status |
|---|---|---|
| `policy-demo-plan-v1` | `demo-plan-v1` | synthetic-fixture |
| `policy-demo-plan-v2` | `demo-plan-v2` | synthetic-fixture |
| `policy-gen-plan-flat-v1` | `gen-plan-flat-v1` | synthetic-fixture |
| `policy-gen-plan-hdhp-v1` | `gen-plan-hdhp-v1` | synthetic-fixture |
| `policy-gen-plan-shift-v1` | `gen-plan-shift-v1` | synthetic-fixture |
| `policy-gen-plan-shift-v2` | `gen-plan-shift-v2` | synthetic-fixture |

These six records reference plan-owned benefit configuration. They are not a loaded healthcare-regulation corpus, approved clinical guidelines, or independently executable rules. The synthetic source record is the evidence for exact values and applicability.

## 4. Scenario coverage

### Curated P01–P16 cases

The UI has human-language questions and background claim selection for these cases. Instructions about source references and recorded/reconstructed evidence are injected by the backend. The [test catalog](pricing-scenarios.md) contains the complete questions and evaluator checks.

| Case | Scenario | Claim references |
|---|---|---|
| P01 | Understand a $75 copay | `demo-claim-current` |
| P02 | Same medicine, higher copay | `demo-claim-current`, `demo-claim-prior` |
| P03 | A generic treated as premium | `demo-claim-current` |
| P04 | Approved, but still paying $75 | `demo-claim-pa` |
| P05 | Identify the medicine on a charge | `demo-claim-missing-drug` |
| P06 | Find the plan behind a charge | `demo-claim-missing-plan` |
| P07 | Find a prescription under my account | `demo-claim-missing-member` |
| P08 | Missing my insurance details | `demo-claim-missing-all-refs` |
| P09 | Was prior approval needed? | `demo-claim-no-pa` |
| P10 | An unrecognized prescription charge | `demo-claim-unresolved-identity` |
| P11 | What went toward my deductible? | `gen-claim-0001-ded-full-absorb` |
| P12 | How was this prescription priced? | `gen-claim-0002-price-exception-unit` |
| P13 | Still paying after meeting my deductible | `gen-claim-0003-coins-after-ded-met` |
| P14 | One fill costs $90, the next is free | `gen-claim-0006-oop-max-reached`, `gen-claim-0007-oop-exhausted` |
| P15 | My copay went from $25 to $120 | `gen-claim-0008-plan-shift-flat-to-ded`, `gen-claim-0009-plan-shift-deductible` |
| P16 | Why is my percentage share $5? | `gen-claim-0013-coins-min-floor` |

### Additional data-backed storylines

The Appendix inventories every claim, including cases outside P01–P16. These additional storylines have data in Atlas, but their presence does not imply completed automated evaluation. To test a comparison not in the curated dropdown, include the relevant claim IDs in the question; the current coordinator gives explicit references precedence over the selected scenario.

| Storyline | Records | What to investigate |
|---|---|---|
| Price exception versus member impact | `gen-claim-0004-price-exception-no-member-impact`, `gen-claim-0018-member-d-percent-exception`, `gen-claim-0030-member-e-percent-price`, `gen-claim-0049-member-h-percent-price` | Separate the allowed-price exception from member cost-sharing and caps. |
| Repeat fills with different quantities | Generated pairs 0004/0005, 0018/0019, 0030/0031, 0049/0050 | Same product does not imply the same quantity or allowed amount; compare source inputs. |
| Generic/brand flat-copay exceptions | Generated 0010/0011 and 0040/0041 | Compare product-specific fixed copays under the same plan. |
| Copay limited by allowed amount | Generated 0014 and 0044 | Confirm a recorded $6 payment rather than assuming a configured $10 copay always applies. |
| Multiple missing references | Generated 0023–0026, 0038–0039, 0045–0048 | Resolve only exact alternate identifiers and applicable coverage. Full reconstruction may require historical evidence absent from the partial trace. |
| Missing all identifiers with insufficient alternatives | `gen-claim-0022-missing-all-refs` and `demo-claim-unresolved-identity` | Confirm what is recorded; request identifying information rather than guess. |
| Member D lifecycle | Generated 0016–0021 | Price exceptions, post-deductible coinsurance, repeat fills, and recorded OOP exhaustion. |
| Member E lifecycle | Generated 0027–0033 | New member with no seeded member context, partial references, deductible progression, and caps; last record still has an OOP balance. |
| Member F plan transition | Generated 0034–0039 | Historical plan selection, retail/mail quantities, benefit change, and partial references. |
| Member G copay and coinsurance | Generated 0040–0045 | Generic/brand copays, default coinsurance, minimum payment, allowed-amount cap, and missing links. |
| Member H lifecycle | Generated 0046–0052 | Missing-identity combinations, percent-price exception, repeat fills, and residual OOP balances. |

### Labels that must not become assumed answers

The current data contains these important examples:

| Claim | Member payment | OOP remaining before | OOP remaining after |
|---|---|---|---|
| `gen-claim-0006-oop-max-reached` | $90.00 | $90.00 | $0.00 |
| `gen-claim-0007-oop-exhausted` | $0.00 | $0.00 | $0.00 |
| `gen-claim-0020-member-d-oop-max` | $90.00 | $90.00 | $0.00 |
| `gen-claim-0021-member-d-oop-exhausted` | $0.00 | $0.00 | $0.00 |
| `gen-claim-0032-member-e-oop-cap` | $100.00 | $125.00 | $25.00 |
| `gen-claim-0033-member-e-oop-exhausted` | $12.00 | $25.00 | $13.00 |
| `gen-claim-0051-member-h-oop-cap` | $100.00 | $118.00 | $18.00 |
| `gen-claim-0052-member-h-oop-exhausted` | $12.00 | $18.00 | $6.00 |

`gen-claim-0033-member-e-oop-exhausted` and `gen-claim-0052-member-h-oop-exhausted` do **not** demonstrate a zero remaining balance in this snapshot. Their names are scenario labels; their recorded balances and payments determine the supported explanation. No data was corrected as part of this documentation update.

Some generated service dates extend into November 2026, after this October 27 inventory. They are intentional synthetic timelines, not evidence of real completed future transactions. Evaluate historical applicability against each fixture’s service date, not today’s date.

## 5. Revised context-layer responsibilities

### Individual agent memory

Each target domain agent should have its own semantic/procedural memory and decision loop. Semantic memory supplies established definitions and attributed knowledge; procedural memory supplies approved investigation, refresh, and publication procedures. Episodic/taxonomic memory can complement those categories. Private agent memory is not automatically shared merely because domain context is shared.

For stable terminology, reviewed semantic memory may be sufficient. For a member-specific price or coverage answer, retained facts must still be attributable to the relevant claim, plan version, and observation time. Any remembered business fact should carry applicability and freshness information. A memory result is not independent corroboration of the source from which it was extracted.

### Shared context as a runtime cache

`{domain}_context` holds expensive-to-retrieve source facts, selected relationships, optional attributed notes, and reusable findings. It avoids making a slow mainframe or MCP/tool read on every question when the required evidence is sufficiently fresh. Domain agents may reuse one another’s authorized context directly or request another agent’s findings.

Every source field, including `_id`, business subdocuments, source `schemaVersion`, `context` annotations, and `provenance` when present, is copied unchanged at the root. The `operationalSnapshot` wrapper is removed. Enrichments sit alongside those fields: `contextSchemaVersion: 2`, `source`, `resolvedRelationships`, `investigation`, `explanation`, `freshness`, and `revision`. `source.fieldNames` records which fields belong to the source so refreshes can remove stale source fields without removing enrichments. Source/enrichment field collisions fail explicitly. Missing raw identifiers remain absent; inferred links belong in `resolvedRelationships`. Optional `metadata` carries evolving, attributed information. For example, a member’s report of a temporary move belongs primarily to Member context; its Plan implications can reference that statement. No temporary-relocation fixture has been inserted in this dataset.

Refreshing or evicting cached source facts must preserve any annotations or findings that need retention. Whole-document deletion is not an appropriate shortcut when the same context document also contains user-contributed or decision-relevant artifacts.

### Proposed freshness policies — examples, not implemented defaults

| Context | Illustrative policy | Earlier refresh triggers |
|---|---|---|
| Plan | A 90-day budget illustrates months of reuse for sufficiently stable configuration | Plan amendment/correction, a new effective version, or a question requiring current configuration |
| Member | A 2-day budget illustrates more frequent refresh; actual budgets may vary by field and question | Coverage/address changes, relevant source events, or current eligibility requiring fresher evidence |
| Claim | Preserve exact historical adjudication versions; choose a separate freshness budget for live status | Reversal, adjustment, reprocessing, or corrected source evidence |
| Drug | Separate product classification from effective-dated price history | New product information or applicable price changes |
| PA | Evaluate status and effective interval; define refresh policy by decision need | Appeal, override, expiration, or changed authorization status |

Cache age, source version, business effective time, and the question’s freshness requirement are different dimensions. A cache miss, expired budget, source-change notification, or decision-critical field can trigger selective source retrieval. An unavailable source should lead to an explicit limitation or allowed stale response under policy, not an invented verification time.

The current runtime still verifies operational data on reads and before writes. It does not yet implement these age budgets, mainframe load reduction, automatic event invalidation, or memory-first source selection.

### Mainframe write-back and warehouse publication

The target agent can choose a permitted command or scheduled export using its procedure. Authoritative source changes go through the owning domain service/API, with validation, attribution, and any required approval. A user-reported circumstance is not a committed source change. Warehouse publication uses a defined ingestion contract, idempotent batches/checkpoints, and explicit destination/scope. Neither path exists in the current query-only source adapter.

## 6. Proposed demonstrations that still need fixtures or behavior

| Design case | What to show | Missing setup |
|---|---|---|
| M01 — Stable semantic recall | Reviewed definition answered from private domain memory | Seeded, attributable semantic memory and a connected memory service |
| M02 — Warm Plan cache | Fresh plan evidence reused without a raw-source call | Freshness fields/policy, a controllable clock, and source-call measurement |
| M03 — Stale Member cache | Member selects a targeted refresh after the budget expires | Expired cache fixture, changed source version, and explicit refresh policy |
| M04 — Early invalidation | A source event invalidates context before its age budget ends | Change event plus dependency invalidation behavior |
| M05 — Conflicting memory | Current applicable evidence supersedes a stale remembered fact | Seeded stale memory, newer versioned evidence, and supersession policy |
| M06 — Cross-domain reuse | Claim uses Plan/Member context while private memories remain scoped | Independent agent loops and an access-policy demonstration |
| M07 — Source unavailable | Fresh context succeeds; stale critical evidence produces a bounded limitation | Tool/MCP failure fixtures and a stale-response policy |
| M08 — Temporary move | Attributed member statement remains provisional until confirmed | Member note, confirmation state, and optional owner-service response fixture |
| M09 — Authorized source update | Permitted command, acknowledgment, and context reconciliation | Mock owning-domain command service; no raw source writes |
| M10 — Warehouse export | Curated records published on schedule with retry/idempotency | Mock warehouse ingestion endpoint, export procedure, and checkpoint |

These are design targets, not new claims, seeded memories, implemented backend features, or completed tests. The interactive architecture diagram illustrates selected paths without changing the Docker backend.

## 7. Evidence and evaluation boundaries

- P01–P16 are the curated runtime/test catalog; extra fixtures can be selected individually through fallback scenarios. Their full behavior is not automatically validated by being in the dropdown.
- Original source decision artifacts can exist inside `claims_context.investigation.recordedSourceEvidence`, in the generator’s `decision_traces`, and in the archive database. The current repository prefers embedded source evidence, then an exact current trace reference, then the archive fallback. Copies may overlap; retain provenance and inspect which version was used.
- A recorded source artifact describes synthetic adjudication. Model commentary or runtime events describe a later investigation. Neither is private chain-of-thought.
- Existing `rules_policies` documents reference synthetic plan configuration; a matching rule alone does not prove historical rule selection.
- Partial source traces can establish only an outcome and missing inputs. Resolved identities may permit a supported reconstruction, but do not manufacture a recorded decision or historical accumulator.
- Evaluation records and evaluator checks must remain outside agent retrieval. This guide is for developers/evaluators; do not load it wholesale as agent memory or a knowledge corpus.
- Money is stored in integer cents and percentages can use basis points. A 2,000-basis-point coinsurance rate is 20%; an 8,000-basis-point price exception is 80% of the default price.
- The local memory adapter’s existence does not establish connected memory, seeded knowledge, durable extraction, or isolation verified against a live service. This inventory did not call a memory service.

## Appendix A. Every claim and what it contains

Amounts and missing references below come from actual records in the verified snapshot. “Recorded source decision” means a `rule-applied` event exists in the inspected source artifacts; it is not an end-to-end correctness certification. A named case can still contain incomplete, inconsistent, or insufficient evidence.

### Original demonstration and missing-reference cases

| Claim ID | Service date | Member payment | Allowed amount | Missing direct references | Curated cases / recorded content |
|---|---|---|---|---|---|
| `demo-claim-prior` | 2026-09-15 | $25.00 | not supplied | none | P02; copay $25.00 |
| `demo-claim-current` | 2026-10-15 | $75.00 | not supplied | none | P01, P02, P03; copay $75.00 |
| `demo-claim-pa` | 2026-10-16 | $75.00 | not supplied | none | P04; copay $75.00; PA linked |
| `demo-claim-missing-drug` | 2026-10-20 | $75.00 | not supplied | drugRef | P05; copay $75.00; alternate product identifiers supplied |
| `demo-claim-missing-plan` | 2026-10-20 | $75.00 | not supplied | planRef | P06; copay $75.00 |
| `demo-claim-missing-member` | 2026-10-20 | $75.00 | not supplied | memberRef | P07; copay $75.00; alternate member identifiers supplied |
| `demo-claim-missing-all-refs` | 2026-10-20 | $75.00 | not supplied | memberRef, drugRef, planRef | P08; copay $75.00; alternate member identifiers supplied; alternate product identifiers supplied |
| `demo-claim-unresolved-identity` | 2026-10-20 | $75.00 | not supplied | memberRef, drugRef, planRef | P10; copay $75.00; alternate member identifiers supplied; alternate product identifiers supplied |
| `demo-claim-no-pa` | 2026-10-20 | $75.00 | not supplied | none | P09; copay $75.00 |

### Generated cases 0001–0026

| Claim ID | Service date | Member payment | Allowed amount | Missing direct references | Curated cases / recorded content |
|---|---|---|---|---|---|
| `gen-claim-0001-ded-full-absorb` | 2026-10-01 | $60.00 | $60.00 | none | P11; deductible $60.00; OOP remaining after $440.00 |
| `gen-claim-0002-price-exception-unit` | 2026-10-05 | $90.00 | $90.00 | drugRef | P12; deductible $90.00; alternate product identifiers supplied |
| `gen-claim-0003-coins-after-ded-met` | 2026-10-10 | $60.00 | $300.00 | none | P13; coinsurance $60.00; OOP remaining after $290.00; PA linked |
| `gen-claim-0004-price-exception-no-member-impact` | 2026-10-15 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $190.00 |
| `gen-claim-0005-repeat-fill` | 2026-10-20 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $90.00 |
| `gen-claim-0006-oop-max-reached` | 2026-10-25 | $90.00 | $600.00 | none | P14; coinsurance $90.00; OOP remaining after $0.00 |
| `gen-claim-0007-oop-exhausted` | 2026-10-30 | $0.00 | $60.00 | none | P14; zero recorded member payment; OOP remaining after $0.00 |
| `gen-claim-0008-plan-shift-flat-to-ded` | 2026-09-15 | $25.00 | $120.00 | planRef | P15; copay $25.00 |
| `gen-claim-0009-plan-shift-deductible` | 2026-10-15 | $120.00 | $120.00 | none | P15; deductible $120.00 |
| `gen-claim-0010-flat-copay-exception` | 2026-10-02 | $10.00 | $60.00 | none | copay $10.00 |
| `gen-claim-0011-flat-copay-exception-brand` | 2026-10-04 | $40.00 | $300.00 | none | copay $40.00 |
| `gen-claim-0012-default-cost-share` | 2026-10-06 | $24.00 | $120.00 | none | coinsurance $24.00 |
| `gen-claim-0013-coins-min-floor` | 2026-10-08 | $5.00 | $20.00 | none | P16; coinsurance $5.00 |
| `gen-claim-0014-flat-copay-below-allowed` | 2026-10-10 | $6.00 | $6.00 | none | copay $6.00 |
| `gen-claim-0015-missing-member-accumulator` | 2026-10-01 | $60.00 | $60.00 | memberRef | deductible $60.00; alternate member identifiers supplied |
| `gen-claim-0016-member-d-price-exception` | 2026-10-05 | $90.00 | $90.00 | none | deductible $90.00; OOP remaining after $350.00 |
| `gen-claim-0017-member-d-coins-after-ded` | 2026-10-10 | $60.00 | $300.00 | none | coinsurance $60.00; OOP remaining after $290.00 |
| `gen-claim-0018-member-d-percent-exception` | 2026-10-15 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $190.00 |
| `gen-claim-0019-member-d-repeat-fill` | 2026-10-20 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $90.00 |
| `gen-claim-0020-member-d-oop-max` | 2026-10-25 | $90.00 | $600.00 | none | coinsurance $90.00; OOP remaining after $0.00 |
| `gen-claim-0021-member-d-oop-exhausted` | 2026-10-30 | $0.00 | $60.00 | none | zero recorded member payment; OOP remaining after $0.00 |
| `gen-claim-0022-missing-all-refs` | 2026-10-31 | $75.00 | not supplied | memberRef, drugRef, planRef | alternate member identifiers supplied; alternate product identifiers supplied |
| `gen-claim-0023-missing-member-and-drug` | 2026-10-12 | $24.00 | $120.00 | memberRef, drugRef | coinsurance $24.00; alternate member identifiers supplied; alternate product identifiers supplied |
| `gen-claim-0024-missing-member-and-plan` | 2026-10-16 | $48.00 | $120.00 | memberRef, planRef | deductible $30.00; coinsurance $18.00; alternate member identifiers supplied |
| `gen-claim-0025-missing-drug-and-plan` | 2026-10-13 | $40.00 | $300.00 | drugRef, planRef | copay $40.00; alternate product identifiers supplied |
| `gen-claim-0026-missing-all-refs-reconstructable` | 2026-10-14 | $24.00 | $120.00 | memberRef, drugRef, planRef | coinsurance $24.00; alternate member identifiers supplied; alternate product identifiers supplied |

### Generated cases 0027–0052

| Claim ID | Service date | Member payment | Allowed amount | Missing direct references | Curated cases / recorded content |
|---|---|---|---|---|---|
| `gen-claim-0027-member-e-deductible` | 2026-11-01 | $30.00 | $30.00 | none | deductible $30.00; OOP remaining after $470.00 |
| `gen-claim-0028-member-e-missing-drug` | 2026-11-05 | $125.00 | $135.00 | drugRef | deductible $120.00; coinsurance $5.00; alternate product identifiers supplied |
| `gen-claim-0029-member-e-deductible-met` | 2026-11-10 | $60.00 | $300.00 | none | coinsurance $60.00; OOP remaining after $285.00 |
| `gen-claim-0030-member-e-percent-price` | 2026-11-15 | $60.00 | $300.00 | none | coinsurance $60.00; OOP remaining after $225.00 |
| `gen-claim-0031-member-e-repeat-fill` | 2026-11-20 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $125.00 |
| `gen-claim-0032-member-e-oop-cap` | 2026-11-25 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $25.00 |
| `gen-claim-0033-member-e-oop-exhausted` | 2026-11-30 | $12.00 | $60.00 | none | coinsurance $12.00; OOP remaining after $13.00 |
| `gen-claim-0034-member-f-shift-v1` | 2026-09-01 | $25.00 | $120.00 | none | copay $25.00 |
| `gen-claim-0035-member-f-mail-fill` | 2026-09-15 | $25.00 | $360.00 | none | copay $25.00 |
| `gen-claim-0036-member-f-shift-v2` | 2026-10-01 | $120.00 | $120.00 | none | deductible $120.00 |
| `gen-claim-0037-member-f-missing-drug` | 2026-10-15 | $36.00 | $60.00 | drugRef | deductible $30.00; coinsurance $6.00; alternate product identifiers supplied |
| `gen-claim-0038-member-f-missing-member-plan` | 2026-10-20 | $24.00 | $120.00 | memberRef, planRef | coinsurance $24.00; alternate member identifiers supplied |
| `gen-claim-0039-member-f-missing-all-refs` | 2026-10-25 | $12.00 | $60.00 | memberRef, drugRef, planRef | coinsurance $12.00; alternate member identifiers supplied; alternate product identifiers supplied |
| `gen-claim-0040-member-g-flat-generic` | 2026-10-11 | $10.00 | $30.00 | none | copay $10.00 |
| `gen-claim-0041-member-g-flat-brand` | 2026-10-12 | $40.00 | $600.00 | none | copay $40.00 |
| `gen-claim-0042-member-g-default-coinsurance` | 2026-10-13 | $36.00 | $180.00 | none | coinsurance $36.00 |
| `gen-claim-0043-member-g-minimum-coinsurance` | 2026-10-14 | $5.00 | $20.00 | none | coinsurance $5.00 |
| `gen-claim-0044-member-g-copay-cap` | 2026-10-15 | $6.00 | $6.00 | none | copay $6.00 |
| `gen-claim-0045-member-g-missing-drug-plan` | 2026-10-16 | $40.00 | $300.00 | drugRef, planRef | copay $40.00; alternate product identifiers supplied |
| `gen-claim-0046-member-h-missing-member` | 2026-11-01 | $30.00 | $30.00 | memberRef | deductible $30.00; alternate member identifiers supplied |
| `gen-claim-0047-member-h-missing-member-drug` | 2026-11-05 | $132.00 | $180.00 | memberRef, drugRef | deductible $120.00; coinsurance $12.00; alternate member identifiers supplied; alternate product identifiers supplied |
| `gen-claim-0048-member-h-missing-member-plan` | 2026-11-10 | $60.00 | $300.00 | memberRef, planRef | coinsurance $60.00; alternate member identifiers supplied |
| `gen-claim-0049-member-h-percent-price` | 2026-11-15 | $60.00 | $300.00 | none | coinsurance $60.00; OOP remaining after $218.00 |
| `gen-claim-0050-member-h-repeat-fill` | 2026-11-20 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $118.00 |
| `gen-claim-0051-member-h-oop-cap` | 2026-11-25 | $100.00 | $600.00 | none | coinsurance $100.00; OOP remaining after $18.00 |
| `gen-claim-0052-member-h-oop-exhausted` | 2026-11-30 | $12.00 | $60.00 | none | coinsurance $12.00; OOP remaining after $6.00 |

## Appendix B. Raw domain references and evidence availability

A dash means the operational reference is absent or null; it is not a repaired link. Alternate identifiers can support lookup but are not a substitute for a unique match. Context existence is shown as of the same snapshot.

| Claim ID | Member reference | Drug reference | Plan reference | PA reference | Claim context | Source evidence |
|---|---|---|---|---|---|---|
| `demo-claim-prior` | `demo-member-001` | `demo-drug-001` | `demo-plan-v1` | — | present | Recorded source decision |
| `demo-claim-current` | `demo-member-001` | `demo-drug-001` | `demo-plan-v2` | — | present | Recorded source decision |
| `demo-claim-pa` | `demo-member-001` | `demo-drug-001` | `demo-plan-v2` | `demo-pa-001` | present | Recorded source decision |
| `demo-claim-missing-drug` | `demo-member-002` | — | `demo-plan-v2` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `demo-claim-missing-plan` | `demo-member-002` | `demo-drug-001` | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `demo-claim-missing-member` | — | `demo-drug-001` | `demo-plan-v2` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `demo-claim-missing-all-refs` | — | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `demo-claim-unresolved-identity` | — | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `demo-claim-no-pa` | `demo-member-002` | `demo-drug-001` | `demo-plan-v2` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0001-ded-full-absorb` | `gen-member-a` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0002-price-exception-unit` | `gen-member-a` | — | `gen-plan-hdhp-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0003-coins-after-ded-met` | `gen-member-a` | `gen-drug-c` | `gen-plan-hdhp-v1` | `gen-pa-coverage-only` | present | Recorded source decision |
| `gen-claim-0004-price-exception-no-member-impact` | `gen-member-a` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0005-repeat-fill` | `gen-member-a` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0006-oop-max-reached` | `gen-member-a` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0007-oop-exhausted` | `gen-member-a` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0008-plan-shift-flat-to-ded` | `gen-member-b` | `gen-drug-b` | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0009-plan-shift-deductible` | `gen-member-b` | `gen-drug-b` | `gen-plan-shift-v2` | — | present | Recorded source decision |
| `gen-claim-0010-flat-copay-exception` | `gen-member-c` | `gen-drug-a` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0011-flat-copay-exception-brand` | `gen-member-c` | `gen-drug-c` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0012-default-cost-share` | `gen-member-c` | `gen-drug-b` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0013-coins-min-floor` | `gen-member-c` | `gen-drug-b` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0014-flat-copay-below-allowed` | `gen-member-c` | `gen-drug-a` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0015-missing-member-accumulator` | — | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0016-member-d-price-exception` | `gen-member-d` | `gen-drug-b` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0017-member-d-coins-after-ded` | `gen-member-d` | `gen-drug-c` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0018-member-d-percent-exception` | `gen-member-d` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0019-member-d-repeat-fill` | `gen-member-d` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0020-member-d-oop-max` | `gen-member-d` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0021-member-d-oop-exhausted` | `gen-member-d` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0022-missing-all-refs` | — | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0023-missing-member-and-drug` | — | — | `gen-plan-flat-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0024-missing-member-and-plan` | — | `gen-drug-b` | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0025-missing-drug-and-plan` | `gen-member-c` | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0026-missing-all-refs-reconstructable` | — | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0027-member-e-deductible` | `gen-member-e` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0028-member-e-missing-drug` | `gen-member-e` | — | `gen-plan-hdhp-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0029-member-e-deductible-met` | `gen-member-e` | `gen-drug-c` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0030-member-e-percent-price` | `gen-member-e` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0031-member-e-repeat-fill` | `gen-member-e` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0032-member-e-oop-cap` | `gen-member-e` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0033-member-e-oop-exhausted` | `gen-member-e` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0034-member-f-shift-v1` | `gen-member-f` | `gen-drug-b` | `gen-plan-shift-v1` | — | present | Recorded source decision |
| `gen-claim-0035-member-f-mail-fill` | `gen-member-f` | `gen-drug-b` | `gen-plan-shift-v1` | — | present | Recorded source decision |
| `gen-claim-0036-member-f-shift-v2` | `gen-member-f` | `gen-drug-b` | `gen-plan-shift-v2` | — | present | Recorded source decision |
| `gen-claim-0037-member-f-missing-drug` | `gen-member-f` | — | `gen-plan-shift-v2` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0038-member-f-missing-member-plan` | — | `gen-drug-b` | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0039-member-f-missing-all-refs` | — | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0040-member-g-flat-generic` | `gen-member-g` | `gen-drug-a` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0041-member-g-flat-brand` | `gen-member-g` | `gen-drug-c` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0042-member-g-default-coinsurance` | `gen-member-g` | `gen-drug-b` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0043-member-g-minimum-coinsurance` | `gen-member-g` | `gen-drug-b` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0044-member-g-copay-cap` | `gen-member-g` | `gen-drug-a` | `gen-plan-flat-v1` | — | present | Recorded source decision |
| `gen-claim-0045-member-g-missing-drug-plan` | `gen-member-g` | — | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0046-member-h-missing-member` | — | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0047-member-h-missing-member-drug` | — | — | `gen-plan-hdhp-v1` | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0048-member-h-missing-member-plan` | — | `gen-drug-c` | — | — | present | Outcome/input evidence; reconstruction or follow-up required |
| `gen-claim-0049-member-h-percent-price` | `gen-member-h` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0050-member-h-repeat-fill` | `gen-member-h` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0051-member-h-oop-cap` | `gen-member-h` | `gen-drug-d` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |
| `gen-claim-0052-member-h-oop-exhausted` | `gen-member-h` | `gen-drug-a` | `gen-plan-hdhp-v1` | — | present | Recorded source decision |

## Maintaining this guide

Counts, context statuses, and records are a dated snapshot. Refresh the inventory when loaders or investigations add data. Preserve the difference between a data-backed case, the runtime’s actual supported behavior, and a proposed memory/cache demonstration. Documentation changes should not silently fix source records or seed expected answers into agent-visible stores.

## Fixture maintenance

The main Studio reads existing fixtures; these scripts maintain compatible earlier snapshots. They do not constitute a full dataset loader. Database names in this guide are neutral defaults, not evidence that an existing remote database was renamed. Runtime database/index overrides do not change the hardcoded target/archive checks in maintenance scripts; inspect those checks before using another deployment.

Run commands from `context-knowledge-graph-runtime`. Each script defaults to read-only preflight. Review the proposed changes before explicitly adding `--apply`; this writes synthetic fixtures and archives backups. Keep source data and backups separate from evaluator-only answers.

| Script | Purpose |
|---|---|
| `scripts/configure_vector_index.py` | Add purpose/date Vector Search filters while preserving embedding configuration; use `--apply` only after reviewing preflight. |
| `scripts/migrate_rule_fields.py` | Remove obsolete `ref`, flatten `meta` into the root, and reject field collisions. Preserve IDs, rule content, and declared relationships. |
| `scripts/migrate_context_mirrors.py` | Mirror every operational field at the context root, retain enrichments, track source field names, and remove the old wrapper. Reject collisions and verify operational hashes remain unchanged. |
| `scripts/expand_rule_graph.py` | Add 18 synthetic dependency rules and MAC version 3 from October 1, preserving the prior version's content and earlier topology. |
| `scripts/seed_rule_version_example.py` | Add isolated specialty fee-cap versions with caps 150 / 125 / 100 and exclusive boundaries at May 1 and September 1. |

```bash
uv run python scripts/migrate_rule_fields.py
uv run python scripts/migrate_context_mirrors.py
uv run python scripts/expand_rule_graph.py
uv run python scripts/seed_rule_version_example.py
```

Rule-schema and version originals are archived under `context_knowledge_graph_archive.rule_schema_backups`; context originals use `context_mirror_backups`. Reports are written locally under ignored `data/`. Structural migration does not revalidate previously stored findings. Root-mirror migration preserves source `_id` values and uses `contextSchemaVersion: 2` separately from a source schema version.

The old root-level `scripts/reorganize_atlas_context.js` is a historical v1 migration, superseded by the root-mirror migration. Do not use it to create wrapped context records. Superseded documentation is retained only in an ignored local archive.
