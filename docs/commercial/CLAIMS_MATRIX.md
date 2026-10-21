# Capability and claims matrix

Evidence baseline: September 29, 2026. Check the running release and source manifest before making a present-tense operational statement. “Implemented” refers to code and recorded checks, not independent customer acceptance.

| Capability | Status and supportable statement | Boundary | Evidence |
|---|---|---|---|
| Public real-data website/API | Live historical federal explorer, state count inference and Nebraska screening; anonymous verification passed on revision geocrash-00002-vkd | 2021–2024 observations; frozen 2025 projection, not current incidents or forecasts; no agency validation | [Public deployment](../PUBLIC_DEPLOYMENT.md) |
| State annual count model | Executable Poisson model; held-out 2024 MAE 34.82 versus 41.96 prior-year baseline | One held-out year across 51 jurisdictions; count burden, not traffic-normalized risk | [Model implementation](../../safety/public_data.py) |
| Road runtime inference | Replays fitted NB/EB calculation for all 11,048 stored roads, max difference approximately 6.72e-11 | Input vintage and statistical limitations remain; no arbitrary uploaded-road endpoint | [Inference](../../safety/inference.py) |
| Synthetic demonstration | Implemented: 24 fictional corridors with explicit synthetic labels | Invented counts, exposure, predictions and intervals; no trained-model or real-road evidence | [Generator](../../safety/demo.py), [demo script](DEMO_SCRIPT.md) |
| Release integrity and packaging | Implemented artifact-hash/manifest audit and allowlisted code/documentation ZIP with checksum manifest | Technical success retains commercial readiness false; no software license grant, security certification, or data rights implied | [Release tooling](../../safety/release.py), [operations](../OPERATIONS.md) |
| Serving and recovery checks | `/ready`, lighter `/api/safety/readiness`, smoke script, and code-traffic rollback helper implemented | Metadata-only API checks do not rehash source files; code rollback does not restore shared data or jobs; no recovery-time guarantee | [Operations](../OPERATIONS.md) |
| Fatal-crash ingestion | Implemented: 153,273 national FARS records ingested for 2021–2024 | National ingestion is not a national exposure-based screening network | [Methods](../SAFETY_ENGINE.md), [source manifest](../../data/safety/fars-manifest.json) |
| Nebraska road screening | Implemented: 11,048 supplied segments and 44,192 road-years | 650/835 Nebraska fatal crashes matched; 185 excluded | [Methods](../SAFETY_ENGINE.md) |
| Exposure normalization | Implemented: vehicle-mile denominators and rates | 2025 AADT is a proxy for historical crash years; no verified historical-risk claim | [Traffic manifest](../../data/safety/aadt-manifest.json) |
| SPF and EB | Implemented experimental count model and EB screening | Not HSM-calibrated or agency-validated; conditional intervals omit several uncertainty sources | [Methods](../SAFETY_ENGINE.md) |
| Expert mixture | Implemented development comparison: 2.10% temporal and 0.714% spatial deviance reduction versus NB | Small internal gains; mixed capture performance; no final challenger promotion | [Advanced models](../ADVANCED_MODELS.md), [benchmark](../../data/safety/advanced-benchmark.json) |
| Countermeasure economics | Implemented conditional CMF 4737 scenario | Not verified local treatment suitability, guaranteed savings, or measured crash reduction | [Methods](../SAFETY_ENGINE.md) |
| Recorded behavior | Implemented 260 aggregate FARS cohorts | Describes fatal-crash records with substantial unknowns; no individual intent/propensity inference | [Advanced models](../ADVANCED_MODELS.md) |
| Live data | NOAA weather alerts connected; refresh and freshness reporting implemented | Weather alerts are not crash detections. Authorized incident adapter is not configured | [Operations](../OPERATIONS.md) |
| Private cloud service | Authenticated Google Cloud deployment verified in a dated report | Not Google endorsement, uptime SLA, multi-tenant certification, or partnership | [Deployment evidence](../../outputs/reports/CLOUD_ADVANCED_VERIFICATION.json) |
| Storage/integration | BigQuery data loads verified; optional PostGIS implementation exists | PostGIS has not been integration-tested against a provisioned instance | [Procurement](../PROCUREMENT.md), [operations](../OPERATIONS.md) |
| Commercial export | Unknown source rights cause the commercial-export path to reject delivery | A permitted technical path is not a substitute for an actual agreement | [Procurement](../PROCUREMENT.md), [source register](../../data/safety/aadt-manifest.json) |
| Research neural models | Implemented and measured in a separate local research workflow | Noncommercial data/weights excluded from the commercial safety service; mixed results | [Advanced models](../ADVANCED_MODELS.md), [Omaha study](../OMAHA_STUDY.md) |
| RoadWorld foundation model | Detailed proposed architecture and disabled configuration | No trained model, transfer benchmark, validated novelty, or performance claim | [Architecture](../FOUNDATION_ARCHITECTURE.md), [proposal configuration](../../configs/foundation/roadworld_scratch.json) |
| OpenJEV | Reference inspected for typed-choice design | Its published weights are not included in the commercial lineage; OpenJEV is distinct from JEPA | [Architecture, source review](../FOUNDATION_ARCHITECTURE.md) |
| Customer impact | Pilot protocol and buyer materials prepared | No signed pilot, revenue, agency endorsement, or observed intervention outcome | [Pilot protocol](../PILOT.md), [SOW template](PILOT_SOW.md) |

## Wording checks for proposals and slides

| Avoid | Use instead |
|---|---|
| “Predicts crashes with X% accuracy” using zero-heavy count MAE | “Reports count deviance, calibration, and shortlist capture against named baselines on the stated holdout” |
| “Knows which drivers are distracted” | “Summarizes recorded FARS distraction factors, including unknowns” |
| “Saves $X / prevents Y deaths” from the calculator | “Estimates conditional scenario benefits under the listed applicability and cost assumptions” |
| “Commercial-ready Nebraska data” | “Commercial reuse requires provider confirmation or an approved replacement” |
| “Our foundation model powers the engine” | “The operational experiment uses statistical screening; foundation pretraining is proposed work” |
| “Google-backed” | “Deployed on Google Cloud” |
| “Validated by a city” | “Prepared for a city-led evaluation,” until documented acceptance exists |
| “SOC 2 compliant / certified” | Describe specific implemented controls and documented remaining review; no certification is claimed |

Keep provenance beside numbers. Never combine the research classifier's scores, safety count-model scores, and proposed foundation architecture into one product-accuracy headline.
