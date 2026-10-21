# Omaha–Lincoln road-safety pilot proposal

This is a prepared pilot protocol. No city, Nebraska DOT, insurer, Google, or other agency has agreed to participate. No real-world crash reduction or acquisition interest has been demonstrated.

## Question and scope

Can an auditable screening workflow help a transportation analyst shortlist road segments for engineering review more efficiently than raw crash counts? The first geography is Omaha and Lincoln, with the statewide Nebraska network retained as reference exposure. The current FARS outcome is fatal crashes. It cannot support claims about all crashes, injury severities, or imminent individual collisions.

The pilot should have one agency safety analyst, one data steward, and one transportation engineer as reviewers. Seek permission to evaluate an existing agency prioritization workflow. Outreach and data-agreement execution require the user's separate action; this document does not send messages or imply a partnership.

## Data agreement checklist

Before agency record import, document provider, owner, coverage dates, road coverage, permitted purpose, commercial reuse, redistribution, retention, attribution, security requirements, and the approver. Obtain NDOT confirmation for AADT redistribution/commercial use. A public download alone is not a license. Obtain documented 511 access rather than using unapproved endpoints.

Require segment identifiers and versioned geometry, annual AADT or an explicit imputation method, intersection definitions, and crash records with event date, stable ID, coordinates, and KABCO injury severity. Record historical traffic vintages and road changes. Deduplicate overlapping FARS and agency fatal records before any unified analysis. Store personal identifiers separately or remove them; the public demo should publish aggregate road results only.

## Evaluation design

1. Freeze training years, a future holdout year, geography, linkage distance policy, outcome, and exposure assumptions before evaluating rankings. Include zero-crash roads in the eligible network.
2. Audit stratified crash-to-road matches manually, including ramps, divided highways, parallel frontage roads, boundaries, and missing coordinates. Report unlocated, unmatched, and ambiguous counts separately.
3. Compare crash count, exposure-normalized rate, the fitted safety performance function, and Empirical Bayes expected/excess frequency. Report temporal and spatial holdout performance, Poisson deviance, calibration, and uncertainty. Treat exploratory local SPF fitting as a local statistical method until a qualified reviewer validates its facility types and assumptions.
4. Evaluate how many holdout fatal crashes lie within a predeclared top-K shortlist, with uncertainty and road-length/exposure represented. Avoid using future outcomes to select K, tune the model, or adjust the match threshold.
5. Have the engineer review ten proposed locations for data quality and treatment applicability. Record accepted, rejected, already-treated, and unknown results. CMFs support conditional estimates; before/after causal effectiveness needs a separate controlled study.
6. Measure analyst time to produce a reviewed shortlist, usefulness of explanations, corrections requested, and export completeness. Keep a signed review log and publish aggregate results only after agreement.

## Proposed acceptance gates

| Area | Gate to agree with the partner before analysis |
|---|---|
| Rights | Every operational source has documented permitted pilot use; commercial claims wait for explicit reuse rights |
| Provenance | Every ranked segment exposes crash years, AADT vintage, geometry/source versions, and assumptions |
| Exposure | No rate for missing or invalid AADT/length; temporal substitutions explicitly flagged |
| Linkage | Stratified manual audit passes an agency-defined precision target; exclusions are visible |
| Model | No leakage; future/spatial holdouts and baseline comparisons reviewed; no deployment if failure is hidden |
| Operations | Missing feeds visibly stale; latest successful refresh retained; failed jobs alert an owner |
| Workflow | Analyst can reproduce shortlist and countermeasure scenario from frozen inputs |
| Outcome | Engineering review validates usefulness; no prediction of prevented deaths claimed from a demo |

Do not invent numeric performance targets after inspecting results. Let the partner pre-register targets based on its road coverage and decision process. Fatal crashes are sparse, so wider geography or more years may be needed; longer windows require checking road and traffic changes.

## Deliverables and next decision

Produce a data-quality report, frozen model card, baseline comparison, reproducible top-K screening table, ten reviewed treatment scenarios with sensitivity bounds, and a short case study with limitations. A pilot decision is whether the agency wants a broader evaluation or integration. Acquisition, revenue, grant awards, and acceptance at a research venue remain future external outcomes.

For a conference submission, retain the existing research results as a separately licensed study, and write the new FARS/exposure experiment as a reproducible independent analysis. Release code and small synthetic fixtures first; publish road/crash artifacts only when their rights and privacy review permit it.
