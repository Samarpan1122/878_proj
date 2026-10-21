# Phases

- [x] Phase 0 — Environment + streamed ingest
- [x] Phase 1 — Cleaning, duration, temporal features, metro subset
- [x] Phase 2 — National tabular baselines
- [x] Phase 3 — OSM GIS buffer features + leakage-safe neighborhood features
- [x] Phase 4 — NAIP imagery features
- [x] Phase 5 — Metro multimodal ablation A–E
- [x] Phase 6 — Metro regimes, image regimes, hotspots, anomalies, folium map
- [x] Phase 7 — National ML engine (classification, regression, forecasting, clustering, risk index)
- [x] Phase 8 — Web explorer with Google Maps
- [x] Phase 9 — v3 site: 3D map, live weather predictions, simulation, crash replay, leaderboard
- [ ] Stretch — road-graph GNN, object detection, deploy

## Independent safety engine
- [x] Official FARS ingestion and source manifests; separate agency KABCO staging
- [x] NDOT AADT exposure, complete zero-crash road-year panels and conservative linkage
- [x] Experimental NB SPF, temporal/spatial baselines, EB screening and uncertainty
- [x] Sourced CMF benefit-cost scenario with explicit applicability/valuation assumptions
- [x] NOAA snapshots, authorized incident adapter, staleness, drift and candidate-job controls
- [x] FastAPI, optional PostGIS, Docker, CI and meaningful tests (>80% safety coverage)
- [x] Screening UI and independent desktop/mobile finish review
- [x] Google Cloud project and private BigQuery GIS tables
- [x] Cloud Run and scheduled weather/candidate execution verified; report saved
- [x] Pilot and procurement protocol prepared
- [ ] Agency data agreement, historical exposure validation, field-reviewed pilot and commercial release

## Advanced model development
- [x] Outcome-free road context, temporal/spatial challenger benchmark and learned expert mixture
- [x] Research-only deep tabular and mixture-of-experts comparisons with calibration and label-availability embargo
- [x] Official FARS behavioral-factor descriptive analysis with missingness denominators
- [x] Integrate measured results into the workspace; preserve evidence and model approval gates
- [x] Verify advanced inference interface and deploy the updated safety evidence screens

## Omaha research correction and adaptation
- [x] Audit original splits, sparse classes, source/duration shifts and retrospective imagery
- [x] Identify held-out outcome contamination in archived spatial-neighborhood features
- [x] Correct duplicate road-edge density locally, preserving original data and every other feature
- [x] Complete matched fixed/monthly experiments with matured labels and class/uncertainty caveats
- [x] Document measured Omaha evidence and reproducible commands in docs/OMAHA_STUDY.md
- [x] Finish/report corrected frozen A–E temporal/spatial-forward challengers, including classification regressions and simple-baseline duration wins
- [x] Verify all online saved-prediction metrics and the retained final monthly model; earlier monthly weights unavailable
- [x] Verify all ten frozen challenger saved models and their archived metrics
- [x] Final Omaha browser checks passed both frozen protocols, both duration objectives, monthly evaluation and error recovery at 1440px/390px without JavaScript errors or viewport overflow; independent finish review disposition SHIP
- [ ] Independent prospective cohort and useful rare-class performance before operational claims

## Foundation architecture request — 2026-09-29

The user requested a detailed new deep-learning/foundation-model architecture using the linked OpenJEV project and additional ideas. The design is now in `docs/FOUNDATION_ARCHITECTURE.md`, with a machine-readable proposal in `configs/foundation/roadworld_scratch.json` and a link from `agent_rules/architechture.md`. It proposes ~50–55M scratch parameters, bounded road/image/temporal encoders, JEPA/EMA pretraining, exposure-offset NB and survival heads, optional measured-motion and MoE experiments, and a typed decision layer. Four research hypotheses include availability-aware pretraining, exposure factorization, reliability-gated motion transfer and active measurement selection. Data, compute arithmetic, evaluation gates, service/API boundaries, implementation order and acceptance tests are specified.

OpenJEV metadata/card/NOTICE were inspected at revision `0b6bb6e571bc7bcd6f1eb68de706f592f29c6483`: Qwen-derived27B fine-tuned typed-decision weights are CC BY-NC4.0. NOTICE names Qwen3.8 while the config class is Qwen3_5; do not identify the base solely by class name. It is distinct from JEPA and is not included in the proposed commercial lineage. No model weights were downloaded or loaded.

This is **architecture only**: no `roadworld/` implementation, foundation checkpoint, new GPU job, established scientific novelty or commercial validation is claimed. Config execution is disabled and trained_checkpoint is null. Existing safety and research models remain separate. Technical review corrected label maturity wording, pre-encoder masking, live-batch regularization semantics, annual/hourly modes and all-missing attention. Configuration arithmetic and documentation links were checked.

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


## Public 3D homepage restored and market assessment — 2026-09-29 (Sep30 UTC)

- User asked for the cool 3D homepage from localhost8878. Public root now serves `web/public/home.html`, `home.css`, `home.js`: tilted real FARS count columns, locally bundled deck.gl9.1.14, local state boundaries, state/year filters, city camera presets with state-level summaries, cell inspection, tilt/zoom/reset, reduced-motion flights and graphics/data failure recovery. No synthetic replay or noncommercial research data added. Original localhost8878 remains intact.
- Existing full workbench moved to `/explore/`; screening `/screening/`, model evidence `/explore/#models`, API `/docs`. Homepage URL remains https://geocrash-666321636483.us-central1.run.app . Renderer/library license bundled. Data and model hashes unchanged.
- Live revision `geocrash-00002-vkd`, 100% traffic; build `cd00c192-04ef-4769-9729-14beebd7edaf`; tag `20260930015440`; digest `sha256:2177306944c582575b73a43c6777e4e0d8d4def750407fb5f2b7de0b38085215`. Deployment took5m34s including infrastructure provisioning and container startup. First post-rollout road prediction request timed out30s; full repeated anonymous smoke passed. Do not claim a latency SLA.
- Nineteen public API/data tests rerun and passed. Anonymous deployed3D browser checks passed1440/390: WebGL,153273counts,NE2024=223,deep links,tilt/reset,Alaska/Hawaii,error recovery,unavailablegraphicsfallback,noJSerrors/overflow. Existing explorer regression passed atbothsizes. Independent fresh finish reviewer: SHIP, no outstanding material findings. Evidence `outputs/releases/public-3d-{verification,cloud-browser,cloud-service,release-summary,upload-manifest}.json`; local evidence also retained. Public upload48files17MiB, restricted assets excluded. DESIGN/surface briefs/README/operations updated.
- User then asked what is actually new and sellable and requested web search. Researched official procurement, FHWA/vendor capabilities, and Google Research using agent-reach Exa via mcporter and web tools. Finding: useful integrated software, but no established industry-first algorithm or demonstrated competitive advantage. Existing NB/EB, CMF economics, maps/APIs overlap established products; foundation proposal remains untrained. Recommend an explicitly scoped agency-data integration/screening pilot with engineering review and measured analyst-time/decision benefits, then permitted intervention-outcome data and proven cross-agency improvements. No outreach sent or buyer demand claimed.
- Market sources: FHWA Numetric overview https://highways.dot.gov/safety/data-analysis-tools/rsdp/rsdp-tools/numetric ; AASHTOWare Safety Segment https://www.aashtoware.org/products/safety/aashtoware-safety-segment/ ; Google Mobility AI https://research.google/blog/introducing-mobility-ai-advancing-urban-transportation/ ; Monterey2025RFP https://www.tamcmonterey.org/files/a6d1360ae/Traffic%2BCrash%2BDatabase%2BManagement%2Band%2BElectronic%2BCitation%2BReport%2BSystem-%2BRFP.pdf . RFP's$250000 covers broader system plus3yearsupport, not a comparable price for this app or an open opportunity.


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
