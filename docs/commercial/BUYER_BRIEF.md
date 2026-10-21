# GeoCrashAI — auditable road-safety screening

**Help transportation analysts build a reviewable shortlist of roads for engineering investigation.** GeoCrashAI connects fatal-crash records, roadway traffic exposure, statistical screening, and sourced countermeasure scenarios in one analyst workspace.

## The workflow

An analyst selects a geography, compares roads by observed fatal crashes, exposure-normalized rate, and Empirical Bayes excess frequency, then inspects a road's source years and uncertainty. A countermeasure scenario records its applicability assumptions and costs. The resulting evidence supports an engineer's review and a reproducible prioritization discussion.

The initial use case is retrospective network screening. Buyers evaluating all-crash injury risk, real-time collision prediction, or automated road-control decisions would need a different validated scope.

The primary buyer demonstration is the public real-data website and API. The [public website](https://geocrash-666321636483.us-central1.run.app) is live without an account; [anonymous verification and deployment evidence](../PUBLIC_DEPLOYMENT.md) identify the serving release. It presents 153,273 federal fatal-crash records and 166,230 fatalities from 2021–2024 across 50 states and DC, plus the Nebraska road engine. An optional offline fixture remains clearly labeled synthetic.

## What is working

- Official FARS ingestion with source hashes, conservative road matching, and visible unmatched/ambiguous records.
- Complete road-year panels, vehicle-mile exposure, an experimental negative-binomial model, and Empirical Bayes expected/excess frequency.
- An interactive screening workspace and API, with visible data provenance and conditional uncertainty intervals.
- A sourced edgeline-widening economic scenario, recording treatment eligibility and severity-transfer assumptions.
- Public website/API implementation with state-level count inference and Nebraska road inference; separate private Google Cloud operations include NOAA alerts and candidate-model jobs. Research data and noncommercial weights stay isolated.
- A separate synthetic demonstration, artifact-integrity audit, and allowlisted evaluation package without real datasets or credentials.

The September 29, 2026 Nebraska snapshot contains **11,048 road segments and 44,192 segment-year observations**. Of 835 Nebraska fatal crashes in FARS 2021–2024, 650 were matched under the documented road-linkage rules; 185 were withheld as ambiguous or too distant. These exclusions remain visible.

## Evidence and present scope

The public annual count model reports held-out 2024 MAE of **34.82 crashes per jurisdiction**, versus **41.96** for a prior-year baseline. Its serving fit uses 2021–2024 and returns a frozen 2025 projection, not a current 2026 forecast. The single-year evaluation is retrospective evidence, not prospective operational validation. [Public model and deployment](../PUBLIC_DEPLOYMENT.md)

On the internal 2024 holdout, the active statistical model's Poisson deviance was 0.10298 versus 0.10465 for an exposure-only reference. Its count MAE was slightly worse. That supports a transparent evaluation, not a claim of superior operational prioritization. The separately tested expert mixture remains an unpromoted development challenger. [Methods and measured results](../SAFETY_ENGINE.md)

All current traffic counts are from 2025, so historical rates are labeled exposure proxies. NDOT commercial reuse rights need confirmation or replacement with an approved source before commercial delivery. The model is experimental and has not received agency validation. FARS measures fatal crashes, not all crashes or individual driving behavior.

## Proposed first engagement

A bounded pilot would evaluate a named network and decision process using approved data. The agency supplies a safety analyst, data steward, and engineering reviewer. GeoCrashAI supplies the frozen analysis, baseline comparisons, reviewable shortlist, data-quality report, and scenario documentation.

Before analysis, agree what success means: linkage quality, shortlist performance at a fixed road-mile budget, analyst time, reproducibility, and explanation usefulness. A pilot can succeed by producing a trusted, faster review process; whether that happens must be measured. A claim of prevented crashes requires a separate intervention-effectiveness study.

**Suggested next step:** a discovery meeting to define one prioritization decision, its current baseline, available data rights, and the reviewer who would judge a pilot. See the [pilot scope template](PILOT_SOW.md).

## Longer-term development

A proposed multimodal road representation model would combine road graphs, imagery, temporal observations, and optional measured trajectories. It is currently an architecture proposal, with no trained foundation checkpoint or demonstrated transfer capability. It is not needed to run the existing screening workflow. [Foundation architecture](../FOUNDATION_ARCHITECTURE.md)
