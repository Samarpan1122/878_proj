# GeoCrashAI — Session Handoff (full chat log + project state)

## Agency planning implementation — 2026-09-30

Frederik Ramm received the authorized reply in the original Gmail thread, confirmed message `1a0f3ac4d4027c56`. It explains initial crash-coordinate-to-road matching, no independently verified labels, intended agency value and the need to validate routing/financial claims. Payload and receipt are under `geo/GeoCrash-investor-replies-2026-09-30/`.

Implemented `/planning/` and public APIs for treatment portfolio optimization, analyst capacity versus cash calculations, exposure-normalized outcome comparisons, reproducible evidence/report exports, conditional future-AADT projections, interactive coordinate matching/manual audits, supplied-route preference comparison and actual OSRM route alternatives. Historical national and Nebraska model artifacts are unchanged; no new foundation model or live traffic feed is claimed. New compact source-bound geometry covers the 11,048 actual NDOT roads. New OSM routing graph is a separate dated Nebraska network from Geofabrik; risk is an incomplete historical overlay, not an individual crash probability.

Validation at implementation stage: 303 safety tests passed, 91.44% package coverage, followed by targeted checks for private routing authentication and geographic/snap bounds. Local public smoke passed 11 checks; desktop/mobile browser flows passed with no overflow or JavaScript errors. `docs/AGENCY_PLANNING.md` documents methods and remaining external validation. See release records for deployed status; a successful image build alone is not a deployment.

### Deployment and verification completed — 2026-09-30

- Live planning workspace: https://geocrash-666321636483.us-central1.run.app/planning/ . Public revision `geocrash-00003-kh4`, 100% traffic, build `954f909d-27de-4bba-ad7f-b253fb2186ce`, image digest `sha256:31dd37b44df32e68be31f25abf3c7ba8af201b566da08c5380204d6be1b4a02b`. Previous public revision `geocrash-00002-vkd` is the rollback target. Existing 3D homepage, historical counts, model inference and API guards passed anonymous regression.
- Private routing service `geocrash-routing`, revision `geocrash-routing-00002-5fj`, 100% traffic, image digest `sha256:f006cffa31c5d597558e327b30d2a4ee2842cd5157f90e126e5ab28ada379287`, successful corrected build `5cf2b9ff-baba-4514-bb3e-1e07cfba46ed`. URL and explicitly accepted audience: `https://geocrash-routing-666321636483.us-central1.run.app`. Public app obtains identity tokens; only `geocrash-public` has service-level invoker. Direct anonymous403 and authenticated200 verified. CPU1/memory2Gi/min0/max1/concurrency4. No service-account keys created.
- OSRM26.9.0 uses the actual Geofabrik Nebraska2026-09-26 extract, SHA256 `a0caa806aabbe2fb2ef3738cc6af3248f8130021f837d553258b4bc6c6be2273`. Frozen car profile, no live traffic. First routing revision failed because graph files were unreadable by UID65534. Corrected ownership and remote non-root actual-route smoke now included in the build. Source, licensing, image and deployment receipts: `infra/routing/`.
- Anonymous new-release smoke passed12checks including an actual Omaha origin/destination request: two paths about4.91mi/12.72min and5.21mi/13.33min, sampled historical risk coverage92.45%/94.64%, whole-route risk correctlynull. These durations are baseline estimates, not measured live travel. Separate deployed desktop1440/mobile390 browser QA passed13APIresponses, allsevenworkflows, report download, keyboard navigation, noJSerrors and nooverflow. Evidence: `outputs/releases/agency-planning-{cloud-smoke,cloud-browser,public-regression,implementation}.json`. Final32routingtests passed after the303test/91.44%coverage run.
- Remaining external work: live congestion/closure feeds and validated operational routing; permitted agency source data and verified independent matching labels; observed productivity, cash savings and intervention outcomes; prospective forecast validation and actual pilot/customer agreement. The release does not implement network-wide real-time traffic control or a trained foundation model. User inputs/scenarios do not become observed agency facts.
- Disk became full during verification; removed only our temporary duplicate Playwright dependencies and generated SDK bytecode, preserving datasets, source-linked ZIPs and credentials. Set `PYTHONDONTWRITEBYTECODE=1` for subsequent CLI calls when practical. Local planning test server8914 was stopped after verification; public service remains live.

## Public 3D homepage restored and market assessment — 2026-09-29 (Sep30 UTC)

- User asked for the cool 3D homepage from localhost8878. Public root now serves `web/public/home.html`, `home.css`, `home.js`: tilted real FARS count columns, locally bundled deck.gl9.1.14, local state boundaries, state/year filters, city camera presets with state-level summaries, cell inspection, tilt/zoom/reset, reduced-motion flights and graphics/data failure recovery. No synthetic replay or noncommercial research data added. Original localhost8878 remains intact.
- Existing full workbench moved to `/explore/`; screening `/screening/`, model evidence `/explore/#models`, API `/docs`. Homepage URL remains https://geocrash-666321636483.us-central1.run.app . Renderer/library license bundled. Data and model hashes unchanged.
- Live revision `geocrash-00002-vkd`, 100% traffic; build `cd00c192-04ef-4769-9729-14beebd7edaf`; tag `20260930015440`; digest `sha256:2177306944c582575b73a43c6777e4e0d8d4def750407fb5f2b7de0b38085215`. Deployment took5m34s including infrastructure provisioning and container startup. First post-rollout road prediction request timed out30s; full repeated anonymous smoke passed. Do not claim a latency SLA.
- Nineteen public API/data tests rerun and passed. Anonymous deployed3D browser checks passed1440/390: WebGL,153273counts,NE2024=223,deep links,tilt/reset,Alaska/Hawaii,error recovery,unavailablegraphicsfallback,noJSerrors/overflow. Existing explorer regression passed atbothsizes. Independent fresh finish reviewer: SHIP, no outstanding material findings. Evidence `outputs/releases/public-3d-{verification,cloud-browser,cloud-service,release-summary,upload-manifest}.json`; local evidence also retained. Public upload48files17MiB, restricted assets excluded. DESIGN/surface briefs/README/operations updated.
- User then asked what is actually new and sellable and requested web search. Researched official procurement, FHWA/vendor capabilities, and Google Research using agent-reach Exa via mcporter and web tools. Finding: useful integrated software, but no established industry-first algorithm or demonstrated competitive advantage. Existing NB/EB, CMF economics, maps/APIs overlap established products; foundation proposal remains untrained. Recommend an explicitly scoped agency-data integration/screening pilot with engineering review and measured analyst-time/decision benefits, then permitted intervention-outcome data and proven cross-agency improvements. No outreach sent or buyer demand claimed.
- Market sources: FHWA Numetric overview https://highways.dot.gov/safety/data-analysis-tools/rsdp/rsdp-tools/numetric ; AASHTOWare Safety Segment https://www.aashtoware.org/products/safety/aashtoware-safety-segment/ ; Google Mobility AI https://research.google/blog/introducing-mobility-ai-advancing-urban-transportation/ ; Monterey2025RFP https://www.tamcmonterey.org/files/a6d1360ae/Traffic%2BCrash%2BDatabase%2BManagement%2Band%2BElectronic%2BCitation%2BReport%2BSystem-%2BRFP.pdf . RFP's$250000 covers broader system plus3yearsupport, not a comparable price for this app or an open opportunity.

## Public real-data launch — 2026-09-29 (2026-09-30 UTC)

The user requested an actual publicly usable website, engines and APIs with real data, and chose the Google Cloud address. **Live, no login:** https://geocrash-666321636483.us-central1.run.app . Road screening: `/screening/`; interactive API documentation: `/docs`. This supersedes the earlier private/synthetic-first demonstration instructions below.

- New public service `geocrash`, revision `geocrash-00001-rhf`, 100% traffic, public invoker IAM. Cloud Build `0c578d0a-e3cf-49ab-8cff-fea17ec05e9b`; image `us-central1-docker.pkg.dev/geocrashai-safety-20260929/geocrash/public:20260930012337`, digest `sha256:f8d23adf9fa555e1820284c4f906ca891a07aa61243a7e65acb6ec645c0abe6b`. Dedicated `geocrash-public` service account has no runtime project/storage roles; snapshots bundled in image. Private `geocrash-safety` remains owner-only and unchanged.
- Public national artifact: 153,273 real FARS fatal crashes, 166,230 fatalities, 50 states plus DC, 2021–2024. Aggregated map accounts for 114,036 mapped, 38,602 small-cell-suppressed and 635 unlocated crashes. Artifact SHA-256 `e0fe1c528a3e97fb476434906b28a6b6c1fe5c6d277880c8d4bcbe448f0e5943`. National download contains aggregates, not raw crash records. Recorded factors preserve unknown/not-applicable denominators; no inferred psychological traits.
- Serving real state-count Poisson inference, Nebraska exposure-offset NB/Empirical Bayes road inference, and conditional CMF economics. State model held-out 2024 MAE 34.82156 versus 41.96078 previous-year baseline; frozen 2025 projection is explicitly historical, not a current 2026 forecast. All 11,048 road outputs replayed with maximum absolute error 6.721245782159713e-11. Foundation architecture remains unimplemented/untrained; NC research weights are not published.
- New `safety/public_data.py`, `safety/public_api.py`, `safety/inference.py`, `web/public/`, public Docker/build/deploy allowlists, `infra/public-cloud-run.sh`, `scripts/verify_public.py`. Public app includes existing safety routes and screening assets. No uploads, retraining, runtime bucket access or research routes. Request size/rate limits and finite JSON checks are active. Public data/feeds are frozen in the image; existing private scheduled jobs do not refresh this public artifact.
- NDOT's official website-use policy supports informational use at the user's risk: https://dot.nebraska.gov/policies-and-disclaimers/ . This does not establish an unrestricted commercial redistribution agreement. Commercial road export guard remains active. Historical exposure assumptions, agency validation, actual partner/contracts and operational obligations remain open.
- Validation: 195 safety tests passed, 91.01% coverage; explicit audit of 50 pinned runtime distributions reported no known vulnerabilities. Anonymous deployed smoke passed website/assets/docs, totals, maps, both model inference paths, economics, body/year guards and research isolation. Anonymous desktop/mobile browser checks passed map/filter/forecast/error recovery. Evidence in `outputs/releases/public-verification.json`, `public-dependency-audit.json`, `road-inference-replay.json`, and public browser reports.
- Build note: first public build failed because classic Docker applied the private `.dockerignore`. `infra/cloudbuild-public.yaml` now copies `Dockerfile.public.dockerignore` to `.dockerignore` in the ephemeral cloud build context before building. Second build succeeded. Public upload manifest verified 43 files/15.4 MiB, no credentials, raw data or research weights.
- Operations and reproduction: `docs/PUBLIC_DEPLOYMENT.md`; buyer materials in `docs/commercial/`. Use `.cloud-config` with the local gcloud installation, never print credentials. No domain required, no outreach sent, no agency certification or acquisition interest claimed.

## Deployable evaluation release and buyer package — 2026-09-29

The user asked to make the product ready for deployment and company/sales discussions. Implemented a bounded private evaluation release, not a claimed commercially cleared foundation model.

- New `safety/release.py`: offline snapshot/input-hash/source-manifest/evaluation checks; lighter `/api/safety/readiness`; explicit commercial blockers; deterministic allowlisted ZIP with per-file SHA-256. No real data, credentials or research weights in the ZIP. `outputs/releases/geocrash-evaluation.zip` has 65 files, 175,054 bytes, SHA-256 `c04fc7d1a21afc3623d590f09d44c0c0e9ee2307b84aed239bb2e01b1d85a094`.
- New `safety/demo.py`: 24 deterministic fictional corridors, refuses to overwrite nonempty directories. Synthetic UI labels, invented interval wording, source register, scenario JSON and CSV/JSON exports remain explicit. No model is trained by this generator. Real datasets and results remain unchanged.
- Seven buyer documents in `docs/commercial/`: buyer brief, ten-minute synthetic-first demo, pilot SOW/acceptance ledger, discovery and unsent outreach, claims matrix, diligence index and guide. No outreach sent, contracts signed, software license grant selected or partnership invented.
- API hardening: finite nested snapshot/evidence validation, nonempty roads, strict numeric input preservation, optional-feed failure isolation, `/ready` startup health and release metadata. Deployment preflight, code-only data-preserving mode, `scripts/smoke_safety.py`, explicit revision rollback helper. Rollback is traffic/code only; real recovery rehearsal remains external work, not a claimed completed test.
- `requirements-safety.lock` pins 49 Python 3.12-resolved runtime distributions. Resolution vulnerability audit found zero known vulnerabilities; this is not an OS/container audit or certification. Docker and CI use the version constraints. The base image is not digest-pinned and the constraints are not package-hash locks.
- Validation: 169 safety tests, 94.51% package coverage. Extracted ZIP generated its synthetic data and passed audit plus all 169 bundled tests using the existing workspace dependency environment. A research-route test now uses a fixture asset so the safety package need not distribute the research interface. Separate desktop1440/mobile390 browser review: SHIP, scenario and area reset, labeled exports, no JS errors/viewport overflow. DESIGN/surface/sidecar updated.
- Cloud Build `a17747bf-df46-4a16-b56a-d11020a87545` succeeded. Image `us-central1-docker.pkg.dev/geocrashai-safety-20260929/geocrash/safety:20260930010504`, digest `sha256:c8e8f8cbb2eb175263d339dfbe4bc727803fedc50b85cea7d459c5605018de16`, deployed to private revision `geocrash-safety-00003-zzd` at 100% traffic. Previous rollback target `geocrash-safety-00002-bzc`. Both jobs updated to this image; not manually rerun. Used `SKIP_DATA_UPLOAD=true`; existing cloud snapshots/live feeds preserved.
- Authenticated live readiness, 11,048-road screening, economics, model evidence, 260 behavior cohorts, 153,273 warehouse crash rows, IAM/private access, research isolation and commercial guard pass. Cloud snapshot SHA equals local audit. Evidence: `outputs/releases/{release-summary,readiness,cloud-smoke,cloud-verification,local-smoke,synthetic-smoke,bundle-verification,dependency-audit}.json`.
- Synthetic server remains http://localhost:8893 (PID22710 at start; agent may have restarted it). Integrated research remains8878. Private cloud URL https://geocrash-safety-666321636483.us-central1.run.app requires identity; use documented gcloud proxy for browser access.
- Remaining real commercial gates: NDOT/source permission or permitted replacement, approved historical exposure/agency engineering validation, actual partner/SOW and operator/security obligations/software terms. Foundation architecture remains unimplemented/untrained; no new GPU job or acquisition claim.

## Foundation architecture request — 2026-09-29

The user requested a detailed new deep-learning/foundation-model architecture using the linked OpenJEV project and additional ideas. The design is now in `docs/FOUNDATION_ARCHITECTURE.md`, with a machine-readable proposal in `configs/foundation/roadworld_scratch.json` and a link from `agent_rules/architechture.md`. It proposes ~50–55M scratch parameters, bounded road/image/temporal encoders, JEPA/EMA pretraining, exposure-offset NB and survival heads, optional measured-motion and MoE experiments, and a typed decision layer. Four research hypotheses include availability-aware pretraining, exposure factorization, reliability-gated motion transfer and active measurement selection. Data, compute arithmetic, evaluation gates, service/API boundaries, implementation order and acceptance tests are specified.

OpenJEV metadata/card/NOTICE were inspected at revision `0b6bb6e571bc7bcd6f1eb68de706f592f29c6483`: Qwen-derived27B fine-tuned typed-decision weights are CC BY-NC4.0. NOTICE names Qwen3.8 while the config class is Qwen3_5; do not identify the base solely by class name. It is distinct from JEPA and is not included in the proposed commercial lineage. No model weights were downloaded or loaded.

This is **architecture only**: no `roadworld/` implementation, foundation checkpoint, new GPU job, established scientific novelty or commercial validation is claimed. Config execution is disabled and trained_checkpoint is null. Existing safety and research models remain separate. Technical review corrected label maturity wording, pre-encoder masking, live-batch regularization semantics, annual/hourly modes and all-missing attention. Configuration arithmetic and documentation links were checked.

## Current Omaha study continuation — 2026-09-29

The user challenged original Omaha four-class scores and negative duration log-R². This continuation addresses that research task rather than substituting national or official-source results. See `docs/OMAHA_STUDY.md` for measured evidence and reproducible commands.

- Audited all 26,480 Omaha–Council Bluffs/Lincoln rows. The original 21,184/5,296 split crosses December 15, 2019. Source1 share shifts 4.87%→40.75%, median duration 30.08→60.34 minutes, precipitation missingness 78.70%→0.04%. Training class supports are 12/17,574/3,497/101. These are traffic-impact classes, not injury severity.
- Original E spatial-neighborhood features leak held-out outcomes into 6,045–8,565 training rows per fold. Temporal history uses earlier test outcomes for 4,988 test rows and requires explicit online interpretation. NAIP imagery postdates incident year for 25,511 rows (96.34%); no historical prospective-availability claim.
- Corrected reverse-direction OSM double counting in `src/gis.py`, changing only `road_km_per_km2_100/_250/_500`. `outputs/research/metro/metro_features_corrected.parquet` preserves every row, identity and other column; original caches remain intact. Corrected SHA256: `ceb6d8a77ee4f115eefed63cb84567c21d6aa9f0c32101940649e01ca299b4ac`. Audits: `gis_correction.json`, `data_audit.json`. Four GIS regression tests passed.
- `src/metro_online.py` completed 40 periods using only labels whose End_Time preceded each origin. Same 5,296 tests: matched fixed→monthly macro F1 0.40356→0.43734, balanced accuracy 0.46474→0.46814, duration MAE 55.3352→53.4041 minutes, log-R² −0.01441→0.09906. Duration excludes observed Severity, GIS, imagery and cached neighborhood outcomes. Geographic MAE-improvement interval [1.1008,2.8262] minutes; balanced-accuracy interval crosses zero and class-4 recall worsens. `online_verification.json` passed all 12 metric values over 5,296 saved prediction rows and reloaded the final monthly model on its eight evaluation rows. Earlier monthly models were not retained and are not claimed reloaded. Targeted checks: 17 API + six online + four GIS + 12 challenger tests = 39 passed. Omaha browser checks passed at 1440px/390px with no JavaScript errors or viewport overflow; independent finish review disposition: SHIP.
- Corrected frozen A–E benchmark is complete in `outputs/research/metro/benchmark.json`: temporal test 5,296 records, spatial-forward 927 (class supports 15/704/194/14). Temporal B balanced accuracy rises 0.43516→0.52241 but macro F1 falls 0.42442→0.37562; temporal F1 declines across all five feature sets. Spatial B rises 0.40015→0.47349 BA and 0.38294→0.40870 F1, but both intervals include zero; C/D/E lose both classification metrics. Do not claim an overall classification improvement.
- Frozen duration selection gives the simple trailing-year `recent_source_median` full weight, with a global recent-median fallback for imagery-only C. A/B/D/E temporal MAE is 54.3557 minutes and log-R² −0.01326; spatial-forward 62.2006 minutes and −0.02981. This is baseline adaptation, not a neural or multimodal breakthrough. All ten saved-model replays and 12 metrics per artifact pass in `inference_verification.json`; 39 targeted tests pass. Omaha browser checks passed both frozen protocols, both duration objectives, monthly evaluation and error recovery at 1440px/390px with no JavaScript errors or viewport overflow; independent finish review disposition: SHIP. Full A–E tables and qualifications are in `docs/OMAHA_STUDY.md`.
- Frozen controls: training-only preprocessing/history, label-availability embargo, `early_stopping=False`, inner-only model/calibration selection. Severity-known duration differs from online context-only duration; spatial-forward differs from original all-time spatial CV. The new architecture/foundation-model investigation is a separate subsequent workstream; no results or capabilities from it are implied here.
- Noncommercial local research remains separate from active government-source safety models and their Cloud Run deployment. Keep substantial training sequential; do not delete caches. Original ablation tables remain unchanged.

## Advanced modeling continuation — 2026-09-29

The user subsequently requested stronger scores, mixture-of-experts models, deep learning, human-behavior analysis and even a foundation model if useful. Multiple agents implemented and independently reviewed a measured upgrade. There is no pretrained foundation model or inferred driver-intent capability; those claims would require different data and validation.

- **Official-source modeling:** `safety/context.py` derives road geometry and midpoint-neighborhood features without outcomes. `safety/advanced.py` compares exposure, NB, Poisson boosting, a learned logistic expert mixture and historical EB. The real benchmark uses 44,192 segment-years and nested temporal/geographic training. The mixture improves deviance over NB by 2.10% temporally and 0.714% geographically, with marginally positive adjusted bootstrap bounds. Capture metrics do not improve consistently. It remains an unpromoted development challenger; the active NB/EB screening model is unchanged.
- **Recorded behavioral factors:** `safety/behavior.py` joins official accident, vehicle, driver-person and one-to-many distraction tables for 2021–2024. It publishes 260 national/state/year cohorts over 153,273 fatal crashes, including all 835 Nebraska records. Speeding, police-reported alcohol and explicit distraction distinguish yes/no/unknown/not applicable. These are retrospective descriptions, not propensity or causal predictions.
- **Research neural benchmark:** `src/advanced_benchmark.py` trains boosting, a residual MLP, a dense three-expert network and validation-selected blends on 120,000 sampled legacy incidents. It compares temporal and future/geographic splits, with and without reporting-source identity. Training and validation duration labels must mature before the next split boundary. The original boundary-crossing run was stopped and superseded. Neural training selected epoch 1 and stopped after five epochs under a 25-epoch budget.
- **Measured neural result:** with Source included, duration MAE improves from 72.77 to 69.33 minutes temporally, and 79.42 to 70.18 minutes in future unseen areas. Classification still favors boosting. Without Source, temporal boosting reaches 68.36 minutes, so the neural gains must not be advertised as wins across all configurations. Label drift and weak log-duration R² remain material limitations.
- **Usable inference:** `src/advanced_inference.py` and local `POST /api/research/predict` serve the saved research blend without labels. They expose missing/unseen inputs, timestamp extrapolation and artifact provenance; model directories are fixed trusted paths. Exact reload parity for all six recorded metrics across 55,988 evaluations is saved in `outputs/research/inference_verification.json`. Research weights remain noncommercial and excluded from cloud uploads.
- **Artifacts:** `data/safety/advanced-benchmark.json`, `data/safety/behavior.json`, `outputs/research/advanced_benchmark.json`, and `outputs/research/models/`. Safety evidence routes require exact source fingerprints and return 409 when stale. The benchmark CLI reconstructs the panel from verified inputs instead of trusting a stale cache.
- **UI and tests:** safety comparison/behavior sections and research neural comparisons passed desktop/mobile controls, overflow and JavaScript checks. Independent finish review disposition: **ship**. Safety tests: 143 passed, 95.05% coverage. Research benchmark: 13 tests; inference: 15 tests. New methods, measured caveats and inference commands are in `docs/ADVANCED_MODELS.md`.
- **Deployment update:** image `us-central1-docker.pkg.dev/geocrashai-safety-20260929/geocrash/safety:20260929204948`, digest `sha256:5a59fa7b02528ef48debe162e8b7877e74d5dd751529b090b85b0ed1825731dd`, is serving 100% of traffic on private Cloud Run revision `geocrash-safety-00002-bzc`. Authenticated health, screening, economics, static assets, model evidence, 260 behavior cohorts, warehouse counts and production research isolation all passed; see `outputs/reports/CLOUD_ADVANCED_VERIFICATION.json`. Both scheduled jobs use the new image. The earlier successful job executions remain in `CLOUD_VERIFICATION.json`; they were not rerun solely for this UI/report update. Deployment preserves the existing live cloud feed instead of overwriting it with a laptop copy.

The local app remains at http://localhost:8878; use `/safety.html#model-evidence` and `/models.html#advanced-models`. API docs are at `/docs`. No source rights, independent agency validation, secured pilot, revenue or acquisition outcome is implied by these additions.

## Latest continuation — safety engine and Google Cloud (2026-09-29)

The original session below is preserved. The user subsequently asked to implement all seven engine recommendations, explicitly requested multiple agents working in parallel, authorized creation of a new Google Cloud project through the CLI, and said to do the work needed toward sales to states/cities and an eventual acquisition. This is authorization to build/deploy; it is not evidence of commercial rights, a customer, or acquisition interest.

### New implementation

- `safety/` is independent of the Kaggle research models: FARS/NDOT adapters, data provenance/schema checks, conservative 50m road matching with ambiguity exclusion, complete road-year panels, vehicle-mile exposure, experimental NB SPF, temporal/geographic validation, Empirical Bayes frequency/excess/intervals, and explicit countermeasure economics.
- Real official FARS2021–2024 archive ingestion:153,273 national fatal crashes,835 Nebraska;11,048 NDOT road segments.650/835 Nebraska crashes matched(77.8%);92 ambiguous and93 outside50m withheld. All AADT counts are2025 proxies for the historical crash period. No HSM calibration claim.
- CMF4737 is **widen edgelines4in to6in**, CMF0.635, rural2lane fatal+injury, excluding intersection/interchange/winter crashes. Calculator requires eligible fraction, fatalities/crash, applicability and FI→fatal transfer acknowledgment. USDOT VSL$14.2M in2025 dollars. It is a scenario, not a recommendation or guaranteed reduction.
- New UI `web/static/safety.{html,css,js}`. Explicit source years, traffic-vintage warning, readable matching coverage, sortable screening, segment inspector, conditional interval plot, CSV export, guarded economics and source/diagnostic view. Independent finish review: **ship**, desktop1440/mobile390, measured action contrast4.92:1.
- `web.server` now runs FastAPI integrated mode on8878, retaining the legacy homepage, EDA, model pages and endpoints via lazy opt-in research routes. `uvicorn safety.api:app` runs safety-only and is the production entry. Original models/data remain intact. Integrated browser regression passed:15891 national cells,22 model charts,30 EDA charts, map and presets, no page errors.
- NOAA weather alerts fetched live. Agency incident adapter requires an explicit authorized GeoJSON feed configuration; none is configured. Agency KABCO import is staged separately pending coverage/linkage review, never merged blindly with FARS.
- Candidate jobs use a GCS lease, generation preconditions, consistent-source hash/manifest checks and completion markers. Candidate training never promotes the active model. Monitoring reports PSI, missingness and coverage review flags.
- Optional PostGIS import/query and schema are implemented and unit-tested with DB mocks; **no PostGIS instance has been provisioned or integration-tested**. BigQuery GIS tables were actually loaded.
- Latest full safety test run:115 tests passed,95.96% coverage. The14 API tests were rerun after the local legacy-health telemetry fix. The4 original research feature self-checks also passed. GitHub CI configuration exists, but this folder has no `.git` repository or remote, so no hosted CI run is claimed.

### Cloud and access

- New project:`geocrashai-safety-20260929`, project number666321636483. User completed Google OAuth through CLI. Billing linked to the available account.
- CLI installation:`.tools/google-cloud-sdk/bin/gcloud`; config/credentials:`.cloud-config`. Both gitignored; **never print credentials or include these directories in an upload**. The upload allowlist was explicitly verified to exclude legacy data/models and secrets.
- Private bucket:`gs://geocrashai-safety-20260929-data`.
- Private BigQuery tables:`geocrashai-safety-20260929.safety.segments`(11,048 roads) and `.crashes`(153,273 records,635 null-geography records), loaded with explicit GEOGRAPHY/JSON schemas.
- Cloud Run:`geocrash-safety`, region`us-central1`; revision`geocrash-safety-00001-k6b`; image`us-central1-docker.pkg.dev/geocrashai-safety-20260929/geocrash/safety:20260929194125`, digest`sha256:9e34abba81d8df53d6aed704d7013dd0dae1a2d7d68cbf79ccf999c43d55345a`.
- URL:`https://geocrash-safety-666321636483.us-central1.run.app`; alias`https://geocrash-safety-o75l2okkba-uc.a.run.app`. IAM requires authentication; the signed-in owner has explicit invoker permission. Ordinary browser navigation does not attach an identity token. Use the `gcloud run services proxy` command in docs/OPERATIONS.md for browser access.
- **Cloud Run reserves `/healthz`** (Google frontend404 even while healthy). Use authenticated `/health`, `/api/safety/status` for readiness, and `/docs`. Authenticated health/readiness/screening/benefit-cost checks passed. Local `/healthz` still works.
- Cloud Scheduler:`geocrash-feeds` every15min, `geocrash-candidate` Sundays03:00 America/Chicago. Dedicated runtime, job and scheduler service accounts. Service scales0–2 instances,1CPU/1GiB; jobs1CPU/2GiB.
- Combined cloud verification passed: weather `geocrash-feeds-6ph54` and candidate `geocrash-candidate-9hxzj` completed successfully; authenticated API, screening, economics, private IAM and warehouse counts passed. Evidence: `outputs/reports/CLOUD_VERIFICATION.json`. Authenticated static HTML/JS/CSS also passed independent checks. `scripts/verify_cloud.py --execute-jobs` reproduces the checks without printing tokens.
- Vertex AI custom-training submission template exists at `infra/vertex-job.json`; **no Vertex job has been submitted**. Routine candidate jobs run on Cloud Run Jobs.
- Local-only final change accurately reports whether legacy models have loaded in combined mode. Production safety-only behavior is unchanged. Future deployments should build a new immutable image from source.

### Documentation and remaining external work

Start with README.md and docs/SAFETY_ENGINE.md, OPERATIONS.md, PILOT.md, PROCUREMENT.md. DESIGN.md and `.impeccable/design.json` record the implemented visual system. The pilot and procurement documents are plans, not completed agreements.

Remaining commercial prerequisites: confirm NDOT reuse/redistribution rights, obtain agency all-crash records and historical traffic/road geometry, validate linkage and facility-specific SPFs with a transportation engineer, secure an agency pilot, select the code license/release policy, and perform contract/security/operational review. No Waze/511 partnership, field-measured safety effect, revenue, acquisition interest, or Google endorsement exists. The new engine is a tested working foundation, not an already validated commercial safety product.

Disk remains tight(~2.5GiB free). Keep local heavy jobs sequentially; do not delete research/user caches. All large container builds were remote.

---

Hand this file to the next agent. It contains **every user prompt verbatim**, a faithful summary of each response and action, the current state of the code/data/website, how to run it, results, known issues, and the recommended next steps.

- Project root: `/Users/smohanty13/Downloads/Temp/878_proj`
- Date of session: 2026-09-29
- Course context: CSCE 878 (UNL) project, based on `README_GeoCrashAI.md` + `ChatGPT-New chat-20260928-1622.pdf` (same design: "GeoCrashAI: Multimodal Geospatial ML for Traffic Accident Severity, Duration, Risk Regimes, and Spatial Anomaly Detection", RQ1–RQ5)
- Also see `agent_rules/` (architecture, design, memory, phases, prd, rules). The user's global rules require keeping `agent_rules/memory.md` and `agent_rules/pahses.md` updated.

---

## 0. Quick start for the next agent

```bash
cd /Users/smohanty13/Downloads/Temp/878_proj
.venv/bin/python -m web.server            # site at http://localhost:8878  (takes ~60–90 s to load 942k rows)
```

Full rebuild order (each stage caches outputs; run heavy jobs ONE AT A TIME — see §6 disk incident):

```bash
.venv/bin/python -m tests.test_features   # 4 self-checks
.venv/bin/python -m src.ingest            # stream 7.7M-row CSV -> data/processed/{national_sample,metro}.parquet (~5 min)
.venv/bin/python -m src.build_metro       # Omaha+Lincoln: OSM GIS + NAIP imagery + neighborhood (slow: Overpass + NAIP)
.venv/bin/python -m src.models            # national baselines + Omaha ablation A–E
.venv/bin/python -m src.discovery         # regimes, hotspots, anomalies, folium map
.venv/bin/python -m src.engine            # national ML engine used by the website (~15 min)
.venv/bin/python -m src.benchmark         # leaderboard, all metrics (~15 min)
.venv/bin/python -m src.analysis          # EDA + model diagnostic plot data (~10 min)
```

Web pages: `/` (3D map + cards), `/details.html?lat=&lng=&r=&name=` (Deep dive report), `/eda.html` (Explore data), `/models.html` (Models).

---

## 1. Environment facts (important)

- macOS, Apple M4, 16 GB RAM. **Disk is nearly full** (≈4.7 GB free at end of session; started at 1.6 GB).
- Python 3.14 venv at `.venv` created with `uv venv --system-site-packages` so it **reuses system torch 2.13** (do NOT let pip install another torch; torchvision pinned to 0.28 to match).
- No Kaggle credentials on the machine. Data is streamed from a byte-identical Hugging Face mirror (see §3).
- Google Maps key is stored ONLY in `.env` (gitignored) as `GOOGLE_MAPS_API_KEY`, served to the browser via `/api/config`. It was pasted in chat, so the user was told to restrict it (HTTP referrer `localhost:8878/*`, Maps JS + Places + Geocoding + Static Maps). **Never print it.** Enabled/working APIs: Maps JavaScript, Places (New), Geocoding, Static Maps, Street View.
- User hooks: a "Fact-Forcing Gate" hook requires stating facts (callers, schema, user instruction verbatim) before the first Write of a file and before destructive commands. RTK / ponytail / claude-mem plugins are active. The claude-mem `chroma-mcp` process holds the uv cache lock (so `uv cache prune` fails — don't force it).
- Overpass: `overpass-api.de` refused this IP after heavy queries; `src/gis.py` rotates to the `maps.mail.ru` mirror (worked). OSM layers are cached in `data/osm/`.

---

## 2. Chat log — every user prompt (verbatim) and what was done

### Prompt 1
> read both readme and then make it get the dateset download from kaggle etc do everything

**Response/actions:**
- Read `README_GeoCrashAI.md` and the 12-page ChatGPT PDF (same GeoCrashAI plan).
- Found blockers: 1.6 GB free disk (CSV is 3.06 GB), no Kaggle creds (anonymous API returned 404). Found HF mirror `Sanjana7787/us-accidents-2016-2023` with the exact `US_Accidents_March23.csv`.
- Created the venv; torchvision pulled a duplicate torch (556 MB), so it was replaced with torchvision 0.28 against system torch; deleted the unused torch 2.14 uv-cache entries (gate facts given).
- `src/ingest.py`: streams the CSV over HTTP (urllib response, since pandas buffers URLs in RAM), keeps a 10% national sample (772,836 rows) + all rows for Omaha/Lincoln/Bellevue/Papillion/La Vista/Council Bluffs/Dallas/Chicago, plus city counts. Read all **7,728,394** rows.
- Study area: Omaha metro + Lincoln = 26,480 accidents at 8,745 unique locations.
- Wrote:
  - `src/features.py`: clean, duration target, temporal features, leakage-safe neighborhood (only accidents that ENDED before this one STARTED), temporal split.
  - `src/gis.py`: OSMnx roads/intersections + building/parking/green/water/commercial/residential/industrial fractions at 100/250/500 m, nearest road class/speed/lanes, distance to highway; Overpass retry + mirror rotation + per-layer parquet cache.
  - `src/imagery.py`: NAIP via Planetary Computer, 224×224 chips at 0.6 m, NDVI veg/impervious/water fractions + ImageNet ResNet-18 512-d embeddings on MPS; chips never saved.
  - `src/build_metro.py`.
  - `src/models.py`: national baselines; Omaha ablation A–E + buffer scales under temporal and spatial-block CV.
  - `src/discovery.py`: KMeans regimes, image regimes, HDBSCAN hotspots, observed-vs-expected severity anomalies at 500 m/1 km, folium map.
  - `tests/test_features.py`, `run.sh`, `requirements.txt`, `.gitignore`, `agent_rules/*`.
- Bugs fixed along the way: geopandas `intersection(align=False)` type error (switched to vectorized shapely); Overpass refusals (mirror rotation); CARTO tiles now need a key (switched to Esri tiles).

### Prompt 2 (mid-turn)
> how much more time

**Response:** estimated ~40–50 min with a stage table (the Omaha OSM download was the risk).

### Prompt 3 (mid-turn)
> no need to download whole thing just start making ,

### Prompt 4 (mid-turn)
> at end my goal is to make a website where i can write any location on google maps and it can show all the info and nice animations and etc and lot of statistics and etc

**Response/actions:** started the website in parallel: `web/server.py` (stdlib `http.server` + BallTree over all rows; weights: national sample rows ×10, full-metro rows ×1), Leaflet + Chart.js frontend with search, radius, stats, time-lapse replay, hotspots/anomalies.

### Prompt 5 (mid-turn)
> make sure it has time series proper regression , classification clustering etc and lot o things like proper engine improve and enhance the idea at max to whatever you can

**Response/actions:** `src/engine.py`, the national engine:
- severity classifier (HGB),
- duration regressor + 10/90% quantiles,
- monthly grid forecaster (0.25° cells, lags 1/2/3/6/12 + rolling + seasonality, vs seasonal-naive/last-value),
- KMeans regimes (k by silhouette, auto-named),
- out-of-fold P(severe) for an observed/expected risk index.

The website got tabs Overview/Forecast/Predict/Regimes/Models.

### Prompt 6 (mid-turn)
> this is the google maps api AIzaSy…(key redacted)

**Response/actions:**
- Stored the key in `.env` (chmod 600, gitignored) and added the `/api/config` endpoint.
- Tested the APIs (all OK). Integrated Google basemaps (GoogleMutant), Places autocomplete (new API), Geocoder and Street View.
- Warned the user to restrict/rotate the key. A curl that would have echoed the key was blocked by the auto-mode classifier; never print it.
- Then the metro pipeline finished (imagery 100% coverage, NAIP 2022/2023). Ran ablation + discovery, wrote `outputs/reports/RESULTS.md`, verified the website in Chrome.

### Prompt 7
> right now predict seems useless it doesent really give anything significant or etc most of the website is still useless , i need to see outliers, plots eda predictions that would ctually matter and etc live satelittie imagery for somethings and etc and design is too ai ,

**Response/actions:**
- Loaded the `hallmark` design skill and redesigned as **Workbench / Cobalt**: cool near-white paper, hairlines, Space Grotesk + Inter + JetBrains Mono, one cobalt accent, tokens in `tokens.css`.
- New `web/report.py` location report:
  - profile: density percentile vs all US ~1 km cells,
  - when: hour×weekday heatmaps (all / severe / model-expected severe),
  - where: ~110 m spots ranked by O/E z, with Google satellite thumbnails,
  - why: model partial dependence (weather×light, visibility, temperature, road features) + observed tables,
  - outliers: unexpectedly severe, longest impact, IsolationForest,
  - duration histogram + quantile predictions,
  - 12-month outlook with a local backtest vs seasonal naive.
- Fixed blank GoogleMutant styled tiles (use a CSS filter instead of Google styles).

### Prompt 8
> good but now i dont see any modeling and predicting part

**Response/actions:**
- Added an interactive **Predict** section (`/api/scenario`): sliders/presets give the severity distribution vs the spot baseline, P(severe) vs the spot and the US, the attribution of each changed condition in percentage points, and expected delay.
- Added **Models** diagnostics per location: local calibration + AUC, duration predicted vs actual, regime mix, grouped permutation importance (cached to `outputs/tables/engine_importance.csv`).
- Honest finding: `year` is the top feature (severity-label drift across feeds).

### Prompt 9
> r^2 and mae and etc dont see metrcis of different things and if i see its very bad score and and website is still way too complicated i think make it user friendly simple but lot of good things like animations 3d models etc add lot of things

**Response/actions:**
- **Engine v2** (`src/engine.py`):
  - Added the reporting feed `Source` as a one-hot feature.
  - Added out-of-fold ~5 km **location-history encodings** (volume, smoothed severe rate, smoothed mean log duration). They are train-only / OOF, so there is no leakage.
  - The OOF P(severe) model used for anomalies excludes these encodings (context-only expectation).
- `src/benchmark.py` leaderboard (future + random protocols; baselines vs logistic/ridge, RF, HGB, HGB+feed+history; all metrics) → `outputs/tables/leaderboard.json`.
- New simple **3D homepage** (`index.html`, `home.js`, `home.css`, deck.gl 9):
  - 3D national columns that rise and orbit, fly-to on search, local 3D hexagons, hotspot pillars,
  - plain-language cards: risk grade A–F, worst time, watch-out-for, hotspots, next 12 months, 3-tap predictor,
  - "Deep dive" drawer (the old report moved to `details.html`), and a `models.html` page.
- **Disk incident:** the engine and benchmark ran concurrently, swap filled the disk to 0 bytes and the shell became unusable. The retrain crashed with ENOSPC.

### Prompt 10
> delete collima related and etc make space

**Response:**
- The shell was unusable at first, so I gave Terminal commands.
- Once it recovered (gate facts given): `colima delete -f; rm -rf ~/.colima`. That removed 4.9 GB, including all Colima containers/images; user-authorized and irreversible. Free space went to 5.2 GB.
- Reran the engine, then the benchmark, **sequentially**.

### Prompt 11 (mid-turn)
> now delete

**Response:** Colima was already deleted; tried `uv cache prune` (blocked by the claude-mem lock; did not force).

### Prompt 12 (mid-turn)
> not just for map but for car 3d model crash accident etc 3d video of collision and etc  like a foreignsics like predicting future of traffic but live as it not  live data right now

**Response/actions:**
- `/api/live` (`web/report.py: live()`): real current + next-24 h weather from **Open-Meteo** (no key) + the local clock. Gives P(severe) per hour and expected crashes per hour (historical weekday-hour rate × recent volume level). Shown as a "Right now" card with a 24 h risk strip.
- **Live simulation**: an accelerated clock spawns Poisson crashes at historically likely points (pulses + 3D columns + feed). Adaptive span (~15 expected crashes in ~30 s), clearly labelled simulated.
- **3D crash replay** (ScenegraphLayer):
  - satellite close-up; two 3D vehicles collide (side impact if a junction/signal/stop/crossing is typical here, else rear-end), impact burst, facts card; labelled illustrative,
  - vehicle model: `web/static/assets/truck.glb` (Khronos CesiumMilkTruck, CC-BY 4.0), used twice with one tinted red,
  - the CarConcept car failed to load (unsupported KHR material extensions) and was deleted.
- Bugs fixed: TDZ on `flying/replay/sim`, basemap zoom cap (Esri dark max 16, satellite 19), leaderboard NaN → `_clean`, a stale server on the port.
- Note: while testing, the user was interacting with tab `1150169369` (switched to satellite, ran the simulation); it was left untouched.

### Prompt 13
> why did you remove the outliers those are important as well and where are plots of eda and scatter and etc show everything lot of plots somewhere just the exploratory analysis and etc and also for models like models of classification, models of regressions , model for time series, model for clustering etc everything

**Response/actions:**
- The Outliers card is back on the homepage (3 tabs, satellite thumbs, fly-to + focus pillar, human-readable reasons).
- `src/analysis.py` writes `outputs/tables/eda.json` + `model_plots.json`.
- **`eda.html`** (~30 charts):
  - dataset overview + missing %,
  - severity and severity by feed, delay histogram + percentiles by severity,
  - year/month/weekday/hour + severe shares, hour×weekday heatmap,
  - weather/temperature/visibility/humidity/wind histograms and severe-rate bands,
  - 4 scatter plots by severity, road-feature lift,
  - crash-location scatter map, states, cities,
  - Spearman correlation matrix,
  - IQR outlier table, Isolation Forest scatter + top anomalies.
- **`models.html`** rebuilt, one section per family (shared helpers in `plots.js`):
  - Classification: table, ROC, PR, calibration, per-class F1, confusion matrices, permutation importance.
  - Regression: table, predicted vs actual, residuals, residual histograms, MAE by severity, 80% interval coverage.
  - Time series: table, national + 6 busiest cells (actual vs GBM vs seasonal naive), error histogram, scatter.
  - Clustering: table, elbow, silhouette, PCA 2D scatter, sizes/severe rate, profile heatmap.
  - Omaha study tables.

### Prompt 14
> now does it all the features and models and etc make sense as an engine or does it need much more i want to get noticed by google and get accuired

**Response (substance):** strong as a course/portfolio project; **not acquisition-ready**.

Blockers:
1. US Accidents is **CC BY-NC-SA 4.0 (non-commercial)**.
2. Google already owns Waze + Maps traffic.
3. No **exposure normalization** (crashes per vehicle-mile), so density ≠ risk.
4. Severity-label drift (`year` is the top feature).
5. Acquisitions buy traction/data/team, not demos.
6. The replay and simulation are demo flair.

Recommended, in order:
- license-clean data: NHTSA FARS, Nebraska state crash data, 511 feeds;
- AADT/HPMS traffic volume;
- **Empirical Bayes network screening** (Highway Safety Manual);
- **countermeasure ROI** (FHWA CMF Clearinghouse × USDOT crash costs);
- a live pipeline (511, Waze for Cities, NOAA) + retraining/drift monitoring;
- production engineering: FastAPI, PostGIS, Docker, CI, Google Cloud BigQuery GIS / Vertex AI;
- one real pilot (Omaha/Lincoln Vision Zero).

Context given with it:
- Precedents: Waycare → Rekor (2021), StreetLight Data → Jacobs (2022).
- Buyers: DOTs/cities (Safe Streets for All grants), insurers, fleets, AV/ADAS.
- Getting noticed: publish the Omaha study (TRB Annual Meeting / NeurIPS–KDD workshop), open-source cleanly, use the demo for Google Research/Waymo/Maps roles.

Offered to start with the data switch + traffic-volume normalization.

### Prompt 15
> save this entire chat with prompt responses etc everything in an md where this proje ct is so i can hand this to another agent

**Response:** this file.

---

## 3. Data

| Item | Detail |
|---|---|
| Source | Kaggle `sobhanmoosavi/us-accidents` March 2023 release, `US_Accidents_March23.csv`, 7,728,394 rows, 2016-02 → 2023-03. **License CC BY-NC-SA 4.0** |
| Access used | HF mirror `https://huggingface.co/datasets/Sanjana7787/us-accidents-2016-2023/resolve/main/US_Accidents_March23.csv`, streamed; set `GEOCRASH_CSV=/path` to use a local Kaggle download |
| `data/processed/national_sample.parquet` | 10% uniform sample (seed 878), 772,836 rows |
| `data/processed/metro.parquet` | all rows for Omaha, Lincoln, Bellevue, Papillion, La Vista, Council Bluffs, Dallas (130k), Chicago (32k) |
| `data/processed/engine_rows.parquet` | 942,049 cleaned rows (sample w=10 + full metros w=1) + Source, enc_* (OOF), p_severe, regime; ≈7.72M crashes represented |
| `data/processed/{gis,imagery,metro_features}.parquet` | Omaha study features (26,480 rows × 608 cols) |
| `data/osm/` | cached OSM layers (Omaha, Lincoln) |
| External at runtime | Google Maps JS/Places/Geocoding/Static/Street View (key in `.env`), Esri tiles, Open-Meteo weather, Nominatim/Photon fallback |

Dropped columns at ingest: Description, Street, Zipcode, Country, Airport_Code, Weather_Timestamp, End_Lat, End_Lng, Turning_Loop. Distance(mi) is kept but intentionally NOT used (post-hoc/leaky).

---

## 4. Code map

```
src/
  ingest.py       stream CSV -> parquet subsets
  features.py     clean(), weather_group(), neighborhood() (leakage-safe), temporal_split(), feature lists
  gis.py          OSM features at 100/250/500 m (Overpass retry + mirror rotation + parquet cache)
  imagery.py      NAIP chips -> NDVI fractions + ResNet-18 embeddings
  build_metro.py  Omaha+Lincoln multimodal table
  models.py       national baselines + Omaha ablation A–E (temporal + spatial CV)
  discovery.py    regimes, image regimes, HDBSCAN hotspots, O/E anomalies, folium map
  engine.py       national engine v2 (Source + OOF location history), forecaster, regimes, OOF p_severe -> models/engine.joblib
  benchmark.py    leaderboard.json (all metrics, future + random)
  analysis.py     eda.json + model_plots.json
web/
  server.py       stdlib HTTP server; endpoints below
  report.py       per-location analytics: profile/when/conditions/danger/spots/outliers/outlook/diagnostics, scenario(), live()
  static/
    index.html home.js home.css      3D homepage (deck.gl): national columns, fly-to, cards, live, simulation, 3D replay
    details.html app.js style.css    Deep-dive report (Leaflet + Chart.js), accepts ?lat&lng&r&name
    eda.html eda.js                  Explore data
    models.html models.js models.css Models (leaderboard + diagnostic plots)
    plots.js                         shared Chart.js helpers
    tokens.css                       design tokens (Cobalt theme)
    assets/truck.glb                 3D vehicle model
tests/test_features.py   4 self-checks (clean, leakage-safe neighborhood, split order, weather groups + NDVI)
outputs/tables/*          metrics, leaderboard, eda/model plot JSON, hotspots, anomalies, regimes
outputs/reports/RESULTS.md  Omaha study write-up (RQ1–RQ5)
outputs/maps/geocrashai_map.html  folium map
models/engine.joblib
agent_rules/              architecture/design/memory/phases/prd/rules
.hallmark/log.json        design-skill log (Workbench/Cobalt)
```

### API endpoints (`web/server.py`)
| Endpoint | Purpose |
|---|---|
| `GET /api/report?lat&lng&r` | full location report (≈1.5 s) |
| `GET /api/scenario?lat&lng&r&hour&dow&month&weather&vis&temp&Junction&Traffic_Signal&Crossing&Stop&Railway` | what-if prediction + attributions |
| `GET /api/live?lat&lng&r` | live weather (Open-Meteo) → next-24 h predictions |
| `GET /api/national` | ~0.1° grid for the 3D overview |
| `GET /api/leaderboard`, `/api/eda`, `/api/model-plots`, `/api/models` | precomputed JSON |
| `GET /api/config` | browser Maps key (from `.env`) |

---

## 5. Results

### National engine v2 (leaderboard, 300k-row sample)
| Task | Model | Future test | Random split |
|---|---|---|---|
| Severity ROC-AUC (severe vs not) | Majority baseline | 0.500 | 0.500 |
| | Gradient boosting (base features) | 0.727 | 0.852 |
| | **GB + feed + location history (used on site)** | **0.909** | **0.929** |
| Severity macro F1 | GB base → GB+ | 0.276 → **0.428** | 0.455 → **0.606** |
| Delay MAE (min) | median baseline → GB+ | 69.2 → **58.1** | 73.1 → **43.7** |
| Delay R² (log min) | GB base → GB+ | 0.033 → **0.122** | 0.356 → **0.585** |
| Monthly forecast MAE (3,183 cells) | last value / seasonal naive / **GBM** | 23.5 / 27.1 / **21.5** | — |
| Clustering | KMeans k=8 silhouette | 0.204 | — |

Full-data engine: severity AUC 0.887 (future), OOF (spatial-block) AUC 0.847. The 80% delay prediction interval covers **80.3%** of real delays.

### Omaha study (RQ1–RQ5; see `outputs/reports/RESULTS.md`)
- RQ1 yes: OSM GIS context raises severity macro F1 0.414 → 0.523 (spatial CV) and 0.315 → 0.384 (temporal). The 100 m scale is best; adding neighborhood history gives 0.538.
- RQ2 no: GIS/imagery don't help duration; temporal R² is negative (drift).
- RQ3: KMeans regimes (k=4) and imagery regimes (k=5).
- RQ4: 178 HDBSCAN hotspots; 35 anomaly cells at 500 m and 30 at 1 km, with 83% cross-scale agreement.
- RQ5: imagery alone is weak (macro F1 0.376) and adds nothing beyond GIS (ImageNet ResNet-18; a remote-sensing foundation model is the obvious next test).

---

## 6. Known issues / caveats

- **License:** the dataset is non-commercial (CC BY-NC-SA 4.0).
- **Label & coverage drift:** severity labeling and recorded volume change across feeds/years (a big drop after 2019 in many areas); `year` and feed are top features. Forecasts inherit the coverage changes.
- **No exposure normalization** (no traffic volume), so "risk" is density-driven.
- The crash replay and live simulation are **illustrative** (the dataset has no vehicle paths; there's no live crash feed). Live weather is real (Open-Meteo).
- Outside the 4 full metros only the 10% national sample is used (counts shown ×10).
- `server.py` is stdlib, single process, no auth/rate limiting: local use only.
- Tests: only 4 self-checks (the user's global rules ask for 80% coverage; not met).
- **Disk:** ≈4.7 GB free. Running engine + benchmark concurrently filled the disk via swap and made the shell unusable. Run heavy jobs sequentially; stop the web server (≈2–3 GB RAM) before retraining if memory is tight.
- `~/.colima` was deleted at the user's request (Docker images in Colima are gone).
- `uv cache prune` is blocked by claude-mem's chroma-mcp lock; don't force it.
- The Google Maps key was exposed in chat and should be restricted/rotated by the user.

---

## 7. Recommended next steps (from the last answer; the user has not yet chosen)

1. License-clean data: NHTSA FARS (public domain), Nebraska DOT crash data, 511 incident feeds.
2. Traffic volume (FHWA HPMS AADT) → crashes per vehicle-mile.
3. Empirical Bayes network screening (HSM safety performance functions).
4. Countermeasure recommendations with ROI (FHWA CMF Clearinghouse × USDOT crash-cost values).
5. A real live pipeline (511, Waze for Cities, NOAA) + scheduled retraining + drift monitoring.
6. Productionize: FastAPI, PostGIS, Docker, CI + real tests, deploy on Google Cloud (BigQuery GIS / Vertex AI).
7. One pilot (Omaha/Lincoln Vision Zero) + publish the Omaha study (TRB / NeurIPS–KDD workshop).

The last offer to the user: *"Want me to start with the data switch and traffic-volume normalization?"* It is awaiting an answer.
