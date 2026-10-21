# Pilot statement of work — working template

Status: proposal for completion and negotiation, not an executed agreement. Complete the fields and acceptance ledger with the buyer before work begins. The [scientific pilot protocol](../PILOT.md) and [methods](../SAFETY_ENGINE.md) supply technical detail.

## 1. Parties and objective

| Field | To complete |
|---|---|
| Supplier legal name and accountable lead | [name / contact] |
| Customer legal name and sponsor | [name / contact] |
| Customer analyst, data steward, engineering reviewer | [named roles] |
| Geography and network | [segments / coverage / facility types] |
| Supported outcome | [fatal crashes for current engine; any expansion requires a separate reviewed specification] |
| Decision supported | [for example: shortlist locations for engineering investigation] |
| Current comparison workflow | [method / owner / baseline artifact] |
| Start and end conditions | [dates, contingent on data and access readiness] |

Objective: assess whether the screening workflow improves a pre-agreed prioritization process using reproducible evidence. The pilot does not itself establish the causal effect of a road treatment.

A preliminary product demonstration may use the supplied 24-corridor synthetic fixture. Its invented outputs are excluded from all predictive and operational-effectiveness acceptance evidence. The contracted pilot requires approved real data.

## 2. Included work

1. Review the approved source inventory, permissions, network coverage, dates, and linkage design.
2. Create a frozen input manifest and data-quality report, including unmatched records and exposure-vintage gaps.
3. Reproduce agreed baselines and experimental SPF/EB screening under predeclared temporal/geographic evaluation.
4. Deliver a fixed-size or fixed-road-mile shortlist with uncertainty and source provenance.
5. Facilitate engineering review of ten locations, or another count agreed before analysis. Record rejected and inapplicable candidates as well as accepted ones.
6. Document applicable countermeasure scenarios using approved local costs and source evidence; an absent eligible treatment is a valid finding.
7. Measure analyst effort and reproducibility, then deliver a final evidence report and recommendation for the next evaluation or integration step.

All-crash modeling, new live-feed integrations, additional jurisdictions, custom GIS connectors, foundation-model training, and sensitive multi-user production operation require separately scoped work. They are not implicitly included by providing access to the current demonstration.

## 3. Data and access schedule

For each source, record provider, owner, event coverage, geography, release date, permitted pilot use, commercial rights, redistribution terms, retention/deletion, attribution, transfer method, and named approver. A completed inventory is a prerequisite to importing customer records.

Use historical geometry and exposure where available. Explicitly identify substitutions. Overlapping FARS and agency records need deduplication before joint analysis. Personal identifiers are excluded unless a separately approved need and handling plan exist.

Current NDOT commercial terms are unconfirmed. Resolve those terms or replace that input with an approved customer source; do not reinterpret public accessibility as permission. Software ownership/licensing, customer data rights, derivative outputs, and any publication rights must be agreed independently.

The initial deployment model is a private environment for named approved users. The current app has no demonstrated tenant isolation or per-user application role model. A shared multi-customer service is outside this template's default scope.

## 4. Milestones and acceptance evidence

| Milestone | Deliverable | Acceptance evidence | Reviewer |
|---|---|---|---|
| M1 — readiness | Rights inventory, network definition, evaluation plan, access plan | Approved sources and completed thresholds below; no unresolved essential permission | Customer data steward and sponsor |
| M2 — frozen data | Hashed inputs, coverage report, linkage audit | Agreed completeness and linkage thresholds met or written stop decision | Data steward and engineer |
| M3 — analysis | Baselines, holdout results, reproducible shortlist | Metrics reproduced; losing results retained; no prohibited leakage | Engineer and analyst |
| M4 — workflow review | Review log, effort measurements, eligible scenarios | Agreed user tasks completed; assumptions and corrections recorded | Analyst and engineer |
| M5 — closeout | Final evidence report, operational handover or data return | Acceptance decision and remaining risks recorded | Sponsor |

Fill these criteria **before holdout evaluation**. A blank criterion is not an accepted threshold.

| Acceptance item | Agreed measure/threshold | Evidence | Decision owner |
|---|---|---|---|
| Data coverage | [years, roads, outcome completeness] | Source coverage audit | [name] |
| Road linkage | [audit sample design, precision target, exclusion rule] | Reviewed match sample with numerator/denominator | [name] |
| Exposure quality | [permitted vintage gaps and missingness] | Road-year vintage and denominator report | [name] |
| Baseline comparison | [metric, practical tolerance, uncertainty approach] | Frozen holdout report | [name] |
| Shortlist usefulness | [road-mile budget or K, review criteria] | Blind or consistently scored review log | [name] |
| Analyst effort | [task definition, repeated measurement, target] | Timing log against current workflow | [name] |
| Reproducibility | [approved rerun and output tolerance] | Manifest and independent rerun | [name] |
| Operations | [refresh expectations, restoration drill, response ownership] | Logged test results | [name] |

Fatal events may be too sparse for a precise predictive conclusion. Agree in advance how an inconclusive result affects scope, payment, and the next decision. Do not adjust acceptance targets after inspecting outcomes.

## 5. Responsibilities and service boundaries

The supplier operates the agreed workflow, documents assumptions, reports failures, and provides the agreed support window. The customer supplies authorized data, resolves local interpretation, and retains engineering and policy decisions. A named reviewer approves any model promotion. Model candidates do not promote automatically.

Complete: support hours [ ], incident contact [ ], notification commitment [ ], maintenance window [ ], recovery target [ ], backup ownership [ ], approved region [ ], log retention [ ], data deletion/return deadline [ ]. These are proposed contract fields, not existing service guarantees. Security requirements must be reviewed against the actual deployment before commitment.

## 6. Commercial schedule and change control

Proposed negotiable structure: a fixed pilot fee divided across agreed milestones, followed only by mutual agreement on ongoing software, hosting, or support. Complete total fee [ ], payment milestones [ ], cloud-cost responsibility/cap [ ], taxes [ ], acceptance/rework period [ ], and cancellation/data-return terms [ ]. No amount is quoted by this template.

Changes to outcomes, geography, data volume, integrations, hosting, users, or evaluation design require a written scope adjustment with cost and schedule impact. A pilot fee pays for agreed deliverables; it does not purchase a guarantee of favorable model scores, safety improvement, or acquisition interest.

## 7. Closeout and sign-off

At closeout, preserve the approved evidence set and review log, revoke access as agreed, and return/delete data under the agreed retention schedule. Public case-study use requires separate written permission. Record one outcome: accepted for the agreed pilot scope, accepted with named limitations, further evaluation required, or not accepted with reasons.

Supplier representative/date: [ ]

Customer representative/date: [ ]

This template must be incorporated into the parties' chosen agreement and completed procurement process; it does not select legal terms on their behalf.
