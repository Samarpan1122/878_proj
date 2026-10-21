# Agency planning implementation

The `/planning/` website connects real Nebraska screening records to bounded decision calculations. It uses the same public API documented at `/docs`. No agency endorsement, realized saving, grant award or crash reduction is implied by a calculation.

## Workflow and API

| Task | Endpoint | Implemented behavior |
|---|---|---|
| Treatment budget | `POST /api/safety/planning/portfolio` | Exact multiple-choice selection maximizing conditional societal NPV within upfront budget; up to 30 candidates; at most one treatment per segment. |
| Analyst productivity | `POST /api/safety/planning/workflow` | Hours released, staff capacity value, explicitly assumed cash realization, first-year cost and break-even workload. |
| Outcome evaluation | `POST /api/safety/planning/outcomes` | Before/after crash rates normalized by VMT, optional comparison group, Poisson intervals and noncausal interpretation. |
| Review package | `POST /api/safety/planning/evidence` | Recomputed scenarios, source and request hashes, readable report, assumptions and unresolved program-specific requirements. |
| Conditional projection | `POST /api/safety/projection` | Existing NB SPF and road-history posterior evaluated for a supplied future-year AADT scenario. |
| Matching coverage | `GET /api/safety/linkage/summary` | Archived pipeline coverage, provenance and thresholds. Coverage is not accuracy. |
| Match coordinates | `POST /api/safety/linkage/match` | Up to 50 caller-supplied coordinates; 20m proximity tolerance and 6m ambiguity margin on source-bound simplified road lines. |
| Manual audit | `POST /api/safety/linkage/review` | Agreement against supplied independent road labels, unresolved fraction and Wilson interval among resolved cases. |
| Route capability | `GET /api/safety/routing/status` | Provider configuration and explicit absence of connected live traffic. |
| Route alternatives | `POST /api/safety/routing/routes` | Operator-configured OSRM baseline car routes, geometry, sampled risk coverage and preference ranking where coverage permits. |
| Personalized comparison | `POST /api/safety/routing/compare` | Time/risk/residential preferences, vehicle/access restrictions, traffic timestamp freshness, and separate illustrative capacity scenarios. |

The website has no default purported customer observations. Treatment eligibility confirmations must be explicitly checked. Analyst-entered costs, reviewed labels, outcome counts and traffic observations remain attributed to the user. Requests do not mutate source artifacts or persist trip/agency measurements. Exports are downloaded to the user's browser; this release is not a shared case-management database.

## Financial and evaluation method

The treatment catalog currently contains FHWA CMF 4737 only. Existing road/fatal-outcome applicability guards still apply. All portfolio alternatives must use a common horizon and discount rate, and 2025 constant-dollar costs. The optimizer constrains upfront implementation cost while including maintenance in life-cycle NPV. It excludes negative-NPV options and never stacks treatments on one segment. Separate road populations are assumed; interactions and overlapping corridors need engineering review.

CMF sensitivity varies the published coefficient by 1.96 standard errors while holding the selected portfolio fixed. This is a sensitivity envelope, not a joint confidence interval and not uncertainty propagation for baseline, exposure, cost or applicability. VSL-based societal benefits are not government cash. Workflow capacity and cash realization are overlapping interpretations and are never summed. Emergency response, property damage and congestion savings are not invented or automatically added to VSL.

Outcome comparisons are descriptive, including when a comparison group is supplied. Rates use the user's VMT denominators. Exact Poisson intervals apply to individual rates; approximate log-rate-ratio intervals require positive counts. Regression to the mean, confounding, overdispersion and reporting changes remain unresolved. No avoided crashes are inferred as a causal treatment effect.

The conditional projection uses calendar days / 365.25 and supplied AADT in the fitted SPF. A Gamma multiplier posterior (shape `1/alpha + observed`, rate `1/alpha + predicted_period`) conditions on the road's archived history. Outputs distinguish a Gamma interval for the mean from a negative-binomial predictive interval for realized counts. This is an executable scenario, not new model training or prospective validation.

## Geometry and routing

Build the compact road geometry without redownloading data:

```bash
.venv/bin/python -m safety.road_geometry --root data/safety
```

`road-geometry.json.gz` binds exact original road-file SHA-256 to every active segment ID. Lines are projected to EPSG:26914 and simplified at 0.5m tolerance. Decode limits, source checks and invalid-geometry guards fail closed. The original historical pipeline still uses unsimplified geometry with 50m/5m matching; this new interactive audit deliberately uses separate, documented conservative thresholds.

Route geometry is sampled roughly every 50m, capped at 2,000 samples and 200km. Samples without a unique nearby road remain unknown. Grade separation, carriageway direction and geometry vintage are not resolved by geometric matching. Historical rate multiplied by traversed distance is an uncalibrated comparison index, not an individual crash probability. Partial coverage produces a covered-portion index and no whole-route risk estimate. A risk-weighted winner requires complete sampled coverage. Residential preference requires supplied classification, rather than silently assuming that unknown roads are nonresidential.

The cached OSM GIS features lack direction/access topology and are not treated as a legal routable graph. An OSRM provider uses an independently built OSM routing graph. Generated routes are restricted to its default car profile; truck dimensions and other profiles are rejected. Baseline OSRM duration is not a current traffic ETA. User-supplied traffic observations have timezone/freshness checks, but their source and accuracy are not independently verified. Hypothetical BPR capacity calculations are shown separately from travel-time ranking and do not establish a network equilibrium or control real traffic.

Configure the operator routing URL with `SAFETY_ROUTING_OSRM_URL`; private Cloud Run deployments additionally use an identity-token audience. Raw origin/destination requests are not persisted by the app. The provider receives coordinates to calculate a path. Cloud Run infrastructure request logs may retain coordinates embedded in provider URLs; application non-persistence does not imply zero infrastructure retention. Keep the routing service private and allow invocation only from the public application's service account. OSRM's public demo server is restricted to noncommercial reasonable use and must not be the commercial deployment's provider.

## Remaining external work

The implementation provides calculations and an inspectable workflow. It cannot establish agency data rights, measured productivity, reliable live traffic, commercial source clearance, causal intervention effects, prospective forecast skill, grant eligibility or a buyer's willingness to pay. Those require approved data and a real pilot. National FARS coverage does not imply nationwide road-level risk or routing coverage. Source and model provenance remain unchanged.
