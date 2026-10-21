# Safety engine: methods and evidence

## Boundaries

The safety package is an independent, experimental Nebraska road-screening engine. Its inputs are NHTSA FARS fatal crashes and an NDOT traffic-count network. It never loads the original Kaggle dataset, research predictions or trained weights. The local research explorer retains those separately licensed capabilities; the deployed service disables them.

FARS is a census of fatal motor-vehicle traffic crashes, not a census of every collision. A row represents a fatal crash; its `fatalities` count is a separate outcome. See [NHTSA FARS](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars). The normalized archive stores one stable ID per crash, source hashes, years, coordinate availability, and an explicit release-status caveat. Downloaded archives may be revised; file hashes freeze the actual inputs used here.

## Exposure and linkage

The [NDOT AADT segment service](https://giscat.ne.gov/dot/rest/services/AnnualAverageDailyTrafficSegmentsDOT/MapServer/0) supplies road geometry, daily traffic and count vintage. Geometry lengths are calculated in EPSG:26914 and converted to miles. Traffic count vintage and crash year remain separate fields.

Each located Nebraska crash is compared with road lines in metres. A match must be within 50 m; a second road within 5 m of the nearest distance causes an ambiguous match to be withheld. This deliberately excludes some junction, frontage-road and divided-highway cases. It is not a validated route/milepost conflation system. Manual auditing is required before decisions.

Every supplied road receives a row for each declared observation year, including zero crashes. Vehicle miles travelled are `AADT × segment length in miles × calendar days`. Rates are fatal crashes per 100 million vehicle miles. Invalid denominators are withheld. Current geometries and 2025 traffic counts are proxies for 2021–2024 conditions; no historical volume growth or road stability is invented.

## Safety performance function and Empirical Bayes

The local negative-binomial SPF predicts mean fatal-crash count:

`mu(segment, year) = length_miles × days/365.25 × exp(b0 + b1 × log(AADT/10000))`

The likelihood fits period-aggregated segment counts with NB2 variance `M + alpha × M²`, where `M` sums annual predictions. This treats segment heterogeneity as persistent across years. Facility-specific road-design predictors are missing, so the implementation is **not an HSM-calibrated SPF**. Boundary fits and convergence failures are reported.

For observed period count `N`, model mean `M`, and dispersion `alpha`, the SPF weight is `w = 1/(1 + alpha × M)`. Expected count is `w × M + (1-w) × N`. Excess frequency subtracts the SPF prediction from this estimate. Annual values divide by observed calendar-year equivalents. Conditional 95% intervals use the Gamma-Poisson posterior; they exclude model-coefficient, linkage and traffic-volume uncertainty. This follows the EB screening principle discussed in [FHWA network-screening guidance](https://highways.dot.gov/safety/data-analysis-tools/systemic/screening-your-network-improve-roadway-safety-performance), with a locally fitted experimental model.

Latest-year validation refits on earlier years. Spatial validation refits with geographically disjoint 0.25-degree groups, holding every year of a road together. Each comparison includes a training-only constant-crashes-per-VMT baseline. Low MAE is not proof of useful ranking when almost all road-years have zero fatal crashes; deviance, calibration, linkage precision and prospective shortlist validation matter.

## Countermeasure appraisal

The initial verified catalog contains [FHWA CMF 4737](https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=4737): widening rural two-lane edgelines from four to six inches, CMF 0.635 for combined fatal/injury outcomes. Its study excludes intersection/interchange and winter-month crashes. It is not automatically applicable to a selected road.

The analyst supplies the eligible fraction of baseline crashes, verifies facility and treatment conditions, and explicitly acknowledges the assumption of transferring that combined-outcome CMF to the fatal-crash subset. Annual avoided fatal crashes are `EB annual baseline × eligible fraction × (1-CMF)`. Fatalities per crash is a separate assumption. The calculator values statistical fatalities at [USDOT's 2025-base-year VSL of $14.2 million](https://www.transportation.gov/office-policy/transportation-policy/revised-departmental-guidance-on-valuation-of-a-statistical-life-in-economic-analysis).

Constant-dollar benefits and annual maintenance costs are discounted over the stated treatment life; capital cost occurs at time zero. The API returns the assumptions, source, dollar year, benefit-cost ratio, net present value and limitations. It does not stack CMFs, include unmeasured injury benefits, or guarantee lives saved. It is a reviewable scenario, not an engineering recommendation.

## Current frozen experiment

The generated snapshot and manifests under `data/safety/` are the authority for counts and results. A source may revise a later download. The study prepared on September 29, 2026 contains:

| Measure | Result |
|---|---:|
| FARS years | 2021–2024 |
| National fatal crashes ingested | 153,273 |
| Nebraska fatal crashes | 835 |
| Matched fatal crashes | 650 (77.8%) |
| Ambiguous matches withheld | 92 |
| Outside 50 m withheld | 93 |
| NDOT road segments | 11,048 |
| Segment-year observations | 44,192 |
| Zero-crash segment-years | 43,574 |
| Exposure proxy segment-years | 44,192 |
| 2024 holdout matched crashes | 175 |
| SPF predicted holdout crashes | 159.95 |
| SPF holdout Poisson deviance | 0.10298 |
| Exposure baseline holdout Poisson deviance | 0.10465 |
| SPF holdout MAE | 0.02795 |
| Exposure baseline holdout MAE | 0.02727 |

The SPF improves deviance modestly but is worse on MAE. It does not establish superior operational ranking or calibrated real-world safety risk. Training a separate model to predict injury classes from FARS-only data would be invalid. The existing research classifier remains explicitly separate.

## Source and operational readiness

NOAA alert refresh is live, timestamped and freshness-checked. An authorized incident feed can be configured but is not connected. An agency KABCO extract can be staged with an agreement and coverage dates; it is not silently blended with overlapping FARS records. Unknown commercial rights block the commercial-export path.

The source register's `commercial_use=false` for NDOT means unconfirmed/uncleared in this product, not a legal conclusion that the state prohibits reuse. Commercial readiness requires provider confirmation, historical exposure/geometry, validated linkage and facility-specific models, an agency engineering reviewer, and the [pilot acceptance process](PILOT.md).
