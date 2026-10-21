# Ten-minute buyer demonstration

Audience: agency safety analyst, engineering consultant, or product/technical buyer. Goal: determine whether an evidence-backed screening pilot addresses the buyer’s prioritization workflow. Use the **public real-data website** for the main presentation. The source observations are historical, not synthetic: 153,273 FARS fatal crashes and 166,230 fatalities from 2021–2024 across 50 states and DC, with a separate Nebraska exposure-based road engine.

Open the [live public website](https://geocrash-666321636483.us-central1.run.app). Anonymous verification passed on revision `geocrash-00002-vkd`; the [public deployment guide](../PUBLIC_DEPLOYMENT.md) records its checks and release identity. Refresh the smoke checks before an important meeting.

## Before the meeting

1. Open the public website in a fresh browser without Google Cloud credentials. Confirm the source years and `/ready`, then test the state/year controls and city camera presets. Open `/explore/` for data tables, `/explore/#models` for inference, `/docs` for APIs and `/screening/` for the road engine.
2. In the data workbench, select Nebraska and 2024. Confirm the displayed cohort contains 223 fatal crashes; reset afterward. Run the state model and inspect a road’s runtime prediction. Distinguish working inference from prospective validation.
3. Keep the [buyer brief](BUYER_BRIEF.md), [methods](../SAFETY_ENGINE.md), [public operations](../PUBLIC_DEPLOYMENT.md), and [claims matrix](CLAIMS_MATRIX.md) available. Confirm their numbers against the current release metadata.
4. Keep the source and prediction periods visible: observations end in 2024; the state model’s frozen projection is for 2025, not a current 2026 forecast. Nebraska’s 2025 AADT is a proxy for earlier exposure.
5. Use approved assumptions for any real countermeasure scenario. Without a reviewed road and eligible crash share, demonstrate the required fields and validation instead of checking an applicability box merely to produce an output.

## Timed walkthrough

| Time | Action | Suggested narration |
|---|---|---|
| 0:00–1:00 | Show the 3D homepage, source period and national totals | “This is a working website and API using actual historical federal fatal-crash records. It helps an analyst examine evidence and form an investigation shortlist.” |
| 1:00–2:00 | Select a state/year, inspect count columns, then open Data for the annual comparison | “The 3D columns aggregate recorded crashes; height uses a square-root scale. City presets move the camera but show state totals. Sparse cells are suppressed, and complete totals are reported separately. These counts measure burden; national traffic exposure is not supplied here.” |
| 2:00–3:00 | Open Models at `/explore/#models`; run the historical state projection and show evaluation | “This executes the deployed count model. Its 2024 holdout MAE is 34.82 crashes per jurisdiction, versus 41.96 for carrying the prior year forward. The serving projection is frozen for 2025; this is not a live 2026 forecast.” |
| 3:00–4:00 | Open recorded factors and source evidence | “These are recorded findings, including unknown and not-applicable categories. They describe fatal-crash reports; they do not identify driver intent or establish causation.” |
| 4:00–5:30 | Follow Road screening; compare counts, rate and excess | “The Nebraska engine covers 11,048 road segments. Counts, exposure-normalized rates and empirical Bayes excess answer different prioritization questions. Historical rates use explicitly labeled 2025 traffic proxies.” |
| 5:30–6:30 | Inspect an actual road and run its prediction | “This recalculates the fitted statistical model for this stored road. We preserve source inputs and uncertainty limitations. It is experimental screening, not an agency-approved safety determination.” |
| 6:30–7:30 | Show a countermeasure scenario and required eligibility | “The catalog links a sourced crash modification factor to stated assumptions and costs. A qualified reviewer must confirm the facility and crash types before applying it. Calculated savings are conditional estimates.” |
| 7:30–8:30 | Open `/docs`, source metadata, and model evidence | “The same capabilities are available through documented APIs. We can identify the deployed artifact and reproduce the model calculation. This public version does not accept data uploads or retrain itself.” |
| 8:30–10:00 | Return to the buyer’s decision and propose a pilot | “We would freeze your approved data and network, compare your current prioritization process, and agree success criteria before examining an untouched evaluation period. Your analysts and engineers review the shortlist.” |

## Present the evidence accurately

The national engine is a statistical count model. The Nebraska engine uses a negative-binomial safety performance function and empirical Bayes screening. Advanced model comparisons remain development evidence, and the RoadWorld foundation model remains an untrained architecture proposal. Do not imply all research models or a foundation model are deployed.

The Nebraska evaluation contains 44,192 segment-years, with 650 of 835 Nebraska FARS crashes linked under conservative rules. A 2025 traffic feed is not verified historical exposure. The fitted SPF is not an agency-calibrated Highway Safety Manual model. The national explorer covers fatal crashes only and cannot demonstrate all-crash injury severity prediction.

NDOT’s [publisher policy](https://dot.nebraska.gov/policies-and-disclaimers/) supports informational use at the user’s risk. The public presentation does not resolve blanket commercial redistribution permissions, grant agency endorsement, or establish operational fitness. Commercial exports remain guarded. Federal aggregate downloads and Nebraska-derived commercial delivery have distinct terms.

A positive benefit-cost ratio is a conditional appraisal, not observed crash reduction. Do not describe private NOAA snapshots or an unconfigured incident adapter as a live nationwide incident product. Check each feed’s actual status before discussing it.

## Questions likely to arise

**“How accurate is it?”** “The annual count model reports a held-out year and a prior-year baseline. The road engine reports count deviance, calibration and shortlist evidence. These are internal retrospective evaluations; your operational acceptance needs an independent agency evaluation.”

**“Can we use it ourselves?”** “The public website and documented APIs can be opened without an account. They serve bounded historical-data queries, statistical inference and scenarios. A contracted deployment needs agreed data rights, access controls, support and acceptance criteria.”

**“Does the AI predict driver behavior?”** “The current factors describe recorded crash findings. A movement model would require licensed timestamped trajectories and separate validation; it has not been trained here.”

**“Can our team inspect the software?”** “An allowlisted evaluation package contains code, documentation, a synthetic fixture generator and checksums. Its distribution terms must be agreed. It excludes account credentials, real datasets and noncommercial research weights.”

**“Can we buy it now?”** “We can define a scoped evaluation and delivery requirements now. Commercial source permissions, software terms, security requirements and acceptance criteria must be settled for your proposed use.”

**“Is Google involved?”** “The application runs on Google Cloud. There is no claimed Google partnership, endorsement, or acquisition discussion.”

## Optional offline backup

A separate synthetic generator provides 24 invented corridors for disconnected workflow demonstrations. See [package instructions](README.md#optional-offline-demonstration). Explicitly introduce the switch to synthetic data; never carry the real-data statistics or model evidence over as results of that fixture.

If the service fails during a meeting, describe any dated documentation or screenshots as recorded evidence and reschedule live verification. Do not present them as current service health.
