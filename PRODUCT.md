# GeoCrash

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The original project serves CSCE 878 reviewers. The user has requested an expansion for transportation safety analysts, with Omaha and Lincoln as the initial study area.

## Product Purpose

Preserve the research explorer while adding exposure-based road screening, empirical Bayes estimates, countermeasure economics, data provenance, and production infrastructure.

## Capabilities and Constraints

The existing national explorer uses noncommercial US Accidents data. The new safety workspace uses a separate FARS and roadway-exposure pipeline. FARS measures fatal crashes only. Exposure from a different year is a proxy and must be labeled. Experimental fitted safety performance functions are not locally validated Highway Safety Manual models. Countermeasure applicability requires engineering review; a modeled benefit is not an observed safety improvement.

## Evidence on Hand

Research results: `outputs/reports/RESULTS.md`. Legacy implementation and limitations: `SESSION_HANDOFF.md`. The user requested creation of a new Google Cloud project with the CLI. No agency pilot agreement, commercial customer, acquisition interest, or validated intervention outcome has been supplied.

## Open Decisions

Agency partner and pilot agreement remain unconfirmed. Nebraska data commercial reuse requires source-specific review. Deployment status must come from actual infrastructure checks.

## Product Principles

- Show units, time windows, and source limitations beside decisions.
- Separate research demonstration from validated operational evidence.
- Preserve the legacy explorer while expanding the analyst workflow.
