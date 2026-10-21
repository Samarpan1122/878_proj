# Advanced model methods and evidence

The project now has an experimental fatal-crash model comparison, a separate research-only neural benchmark, and descriptive FARS behavioral cohorts. These answer different questions. The safety engine predicts segment-year fatal-crash counts. The legacy research benchmark predicts reported traffic-impact severity and disruption duration among recorded incidents. The behavioral report describes recorded factors in fatal crashes. None estimates an individual driver's future behavior or all-crash injury risk.

## Safety models and their measured results

Implementation: `safety/advanced.py`; input: a segment-year panel rebuilt from the snapshot's checksum-verified crash and road files, enriched through `safety/context.py`; report: `data/safety/advanced-benchmark.json`. The CLI reconstructs the panel rather than trusting an old cached panel. The current experiment includes **44,192 segment-years, 11,048 Nebraska road segments, and 650 matched fatal crashes over 2021–2024**. Zero-crash roads remain in the panel. The 650 matched observations differ from the 835 Nebraska FARS fatal crashes because the modeling network excludes unresolved or ambiguous road matches; the model does not recover those excluded events.

| Model | Construction |
|---|---|
| Exposure reference | One training-only fatal-crash rate multiplied by vehicle-miles traveled |
| Negative-binomial SPF | Local NB2 count model using AADT and road length/calendar exposure; the existing experimental statistical reference |
| Poisson boosting | Histogram gradient boosting of crash rate, weighted by exposure; this is equivalent to count Poisson loss with an exposure offset |
| Gated mixture | A logistic gate combines the NB and Poisson-boosting expected counts, followed by a scalar count calibration fitted inside training data |
| Historical EB | Earlier counts on the same road update an NB prior; evaluated only for later years on known roads |

The boosting model uses 100 iterations, learning rate 0.05, at most seven leaves, L2 regularization 10, and no random early-stopping split. Its inputs are log AADT, log segment length, coordinates, sinuosity, vertex density, direction-invariant bearing, neighboring-road midpoint counts at 1 and 5 km, and mean neighboring AADT at 1 km. Geometry features are computed without crash outcomes. A midpoint neighborhood is a road-density proxy, not a verified intersection inventory. Current AADT and road geometry are historical proxies, so the temporal experiment is retrospective rather than a demonstration of what could have been forecast with contemporaneously available road data.

The outer temporal evaluation trains on 2021–2023 and evaluates 2024. Gate fitting uses an earlier-year/last-training-year inner split. The outer spatial evaluation holds out complete 0.25-degree geographic blocks in five folds; its gate uses three inner geographic folds. Imputation, scaling, expert fitting, gating, and calibration stay inside the relevant outer training data. All years of a road share a geographic block. Spatial evaluation measures transfer to unseen geographic blocks over the study years; it is not a combined future-and-new-geography experiment.

The measured mean Poisson deviances below come directly from the saved report; lower is better. Temporal capture is the fraction of held-out crashes represented by the highest-predicted 10% of segment-year rows, not a fraction of road mileage or exposure.

| Model | 2024 deviance | Spatial deviance | 2024 top-decile crash capture |
|---|---:|---:|---:|
| Exposure reference | 0.104654 | 0.100944 | 56.57% |
| Negative-binomial SPF | 0.102980 | 0.098454 | 59.43% |
| Poisson boosting | 0.100573 | 0.097989 | 58.29% |
| Gated mixture | 0.100816 | 0.097751 | 58.86% |
| Historical EB | 0.102702 | Not a cold-start model | 60.00% |

Against the NB reference, the mixture reduces deviance by **2.10% temporally and 0.714% spatially**. Its 2024 expected total is 174.08 versus 175 observed crashes, which measures aggregate agreement, not calibration at every road. The mixture passes the code's internal development rule: positive adjusted paired block-bootstrap lower bounds against both exposure and NB references in both experiments. However, its lower bounds versus NB are only about **0.000051 temporal** and **0.000050 spatial** deviance units. These are modest, near-boundary results, not evidence of a large predictive breakthrough.

The report uses 1,000 paired geographic-block bootstrap replicates and 98.333% intervals. These intervals condition on already fitted folds and omit refitting uncertainty. The 2024 data and corpus have already been inspected during development. Consequently the report marks the mixture an **unpromoted development challenger**, with no final challenger fitted. A new independent agency cohort and named reviewer are required before operational promotion. The active experimental NB/EB snapshot remains separately managed. Small absolute count MAEs are not an accuracy claim: most segment-years have zero fatal crashes, which is why exposure references, count deviance, capture, and uncertainty are reported together.

```bash
.venv/bin/python -m safety.cli --root data/safety benchmark --bootstrap 1000 --spatial-folds 5
```

## Research-only residual MLP and mixture of experts

Implementation: `src/advanced_benchmark.py`. This experiment reads selected raw-feature columns from `data/processed/engine_rows.parquet`; it does not read cached target encodings or earlier model scores. Its input dataset, trained weights, and outputs remain in the noncommercial research workflow. They are excluded from the deployed safety container and safety data bucket.

The model families are implemented locally:

- Histogram gradient boosting supplies separate classification and log-duration regression baselines. A training-prior classifier and weighted training-median duration predictor provide trivial references.
- The residual MLP uses a default width of 48, input projection with LayerNorm/SiLU, a residual two-layer block with dropout 0.1, and two outputs for severity and standardized log duration.
- The soft mixture of experts uses three such residual experts with a small learned gate. All experts are evaluated. The classifier mixes expert probabilities, and the regressor mixes duration outputs; this is dense routing, not a sparse language-model architecture.
- A validation-selected blend compares neural predictions with boosting. Blend weights are selected using validation data, never test outcomes.

Neural optimization uses AdamW, learning rate 0.001, weight decay 0.01, batches of 512, deterministic CPU execution, gradient clipping, and validation-based early stopping. Training loss combines weighted binary cross-entropy with a standardized log-duration Smooth L1 term; the mixture also regularizes aggregate expert usage. The code records the exact configuration, package versions, source/input hashes, model artifacts, temperatures, and chosen blend parameters.

Preprocessing learns medians, numeric scaling, missingness flags, and categorical vocabularies from the training split only. The experiment runs with and without the reporting-feed `Source` feature to expose dependence on feed identity and shifting impact labels. Temperature scaling is fitted on validation predictions. ROC-AUC, precision-recall average precision, Brier score, log loss, duration MAE in minutes, log-duration R², and descriptive context-cohort scores are reported. A positive bootstrap difference favors the candidate; a confidence interval crossing zero is inconclusive. The research intervals are individual comparison intervals, not a familywise significance guarantee across all architectures, source ablations, tasks, and protocols.

Two frozen protocols are defined: chronological 60/20/20 windows, and a stricter future-geography protocol that intersects those windows with disjoint hash-assigned geographic cells. The strict protocol intentionally discards rows outside the corresponding time/geography intersection. Adjacent cells have no spatial buffer, and the source corpus has previously been explored.

The corrected experiment completed on **120,000 sampled records**, width 64 and a maximum budget of 25 epochs. Validation selected epoch 1 for every neural run, and early stopping ended training after five epochs; this is not a claim that 25 epochs were completed. The temporal split contains 71,986 training, 23,995 validation and 24,000 test incidents. Fourteen training and five validation incidents were excluded because their recorded duration crossed the next time boundary. The stricter future/geography split has 44,627 / 4,770 / 3,994 incidents and 531 held-out geographic blocks.

A crash used for training must have ended before the validation boundary, and a validation crash must have ended before the test boundary. This is checked with `Start_Time + duration_min`. Duration ensembles select their neural member and blend weight independently using validation MAE in minutes; classification uses validation log loss. Both duration metrics use the same bounded final prediction. The earlier uncorrected experiment was stopped and superseded.

| Evaluation with reporting-source feature | Boosting duration MAE | Blend duration MAE | Relative reduction | Boosting / blend ROC-AUC |
|---|---:|---:|---:|---:|
| Later incidents | 72.77 min | 69.33 min | 4.73% | 0.799 / 0.799 |
| Later incidents in unseen areas | 79.42 min | 70.18 min | 11.63% | 0.769 / 0.769 |

The paired geographic-bootstrap interval for duration MAE improvement is 1.37–6.10 minutes temporally and 4.32–16.44 minutes in the stricter experiment. These are exploratory per-comparison intervals. Classification selected zero neural weight: boosting remained stronger than either neural network. Log-duration R² remains weak, including −0.004 for the strict with-source blend, so smaller MAE is not evidence of strong explained variance.

Source ablation matters: without feed identity, boosting ROC-AUC drops to 0.682 temporally and 0.675 in unseen areas. However, its temporal duration MAE without Source is **68.36 minutes**, better than the with-source blend's 69.33. The headline neural gains are matched-feature comparisons, not wins over every baseline or feature configuration. All four runs and losing candidates remain visible in the research UI. They cannot be compared directly with the earlier 0.909 research score because features, sampling, target availability and splits differ.

Final evidence is `outputs/research/advanced_benchmark.json`; trusted local model artifacts are under `outputs/research/models/`. All four saved model sets reload with finite predictions. The corrected benchmark has 13 focused tests, including the label-availability embargo and separate duration selection.

Example execution after those checks; the saved report's exact configuration is authoritative:

```bash
.venv/bin/python -m src.advanced_benchmark \
  --rows 120000 --epochs 25 --width 64 --protocol both --source-ablation both \
  --bootstrap-draws 200 --threads 2 \
  --out outputs/research/advanced_benchmark.json \
  --artifact-dir outputs/research/models
```

Only one substantive training job should run at a time on this laptop. Validation is reused for stopping, calibration, and blend selection, so validation scores are optimization results rather than independent evidence. The corrected test remains an internal evaluation of an already explored corpus; external validation is still necessary.

### Saved-model inference

`src/advanced_inference.py` loads only the four fixed trusted local artifact directories. The integrated local app exposes `POST /api/research/predict`; production safety-only mode does not expose this route or package the research weights. Requests contain up to 32 incidents under `records`, using source field names, for example:

```json
{"records":[{"Start_Time":"2023-01-15 08:00:00","Start_Lat":41.2565,"Start_Lng":-95.9345,"Source":"Source1","weather_group":"clear"}]}
```

This is illustrative incomplete context, not a real observed incident or validated current forecast. Omitted optional features use training-fitted preprocessing and are listed in the response. The callable returns calibrated severe-traffic-impact probability, bounded disruption duration in minutes, missing/unseen-feature information, training/evaluation-date extrapolation flags, and model/input/code hashes. Supplied labels or cached prediction fields are ignored and reported. It requires the same timezone-naive local timestamps as the historical source and does not infer a timezone conversion.

```bash
.venv/bin/python -m src.advanced_inference --input incidents.json \
  --output predictions.json --variant temporal-with-source
```

Fifteen inference tests pass. Restored models reproduce all six recorded test metrics exactly across 55,988 evaluations over the four experiment variants; evidence is in `outputs/research/inference_verification.json`. This checks serialization and inference parity, not external accuracy. No research model replaces the legacy predictions automatically or enters the commercial safety deployment.

The research motivation is to compare modest tabular networks and ensembles against strong tree baselines. [TabM](https://arxiv.org/abs/2410.24210) studies parameter-efficient MLP ensembling; [TabArena](https://arxiv.org/abs/2506.16791) emphasizes reliable comparative evaluation and documents validation-set overfitting concerns. Our small residual MLP and dense soft mixture are **not implementations of TabM, TabArena models, or a pretrained foundation model**, and their results cannot be attributed to those papers.

## What the behavioral report actually measures

Implementation: `safety/behavior.py`; aggregate artifact: `data/safety/behavior.json`. The report reads official FARS accident, vehicle, person, and distraction tables for 2021–2024, validates joins and expected vehicle counts, and deduplicates the one-to-many distraction records before aggregating. It exposes national/state/year cohorts, not person-level records.

Speeding uses vehicle `SPEEDREL`; police-reported alcohol uses person `DRINKING` for drivers (`PER_TYP=1`). These are distinct from a measured BAC threshold. Explicit distraction excludes ambiguous inattention/carelessness codes from both the positive and negative categories. These coding choices and the police-judgment interpretation follow the [FARS analytical manual](https://crashstats.nhtsa.dot.gov/Api/Public/ViewPublication/813794), with the report retaining the archived value labels and source hashes for audit.

A fatal crash is positive if any linked vehicle has a positive factor. A negative requires negative evidence for every expected vehicle. Otherwise it remains unknown, except an entirely not-applicable cohort of vehicles. No missing record is treated as a negative. The following counts come from the actual saved artifact.

| Cohort / recorded factor | Yes | No | Unknown | Not applicable | Known denominator |
|---|---:|---:|---:|---:|---:|
| National / speeding | 43,012 | 97,737 | 12,363 | 161 | 140,749 |
| National / police-reported driver alcohol | 28,993 | 61,268 | 63,012 | 0 | 90,261 |
| National / explicit distraction | 6,397 | 31,619 | 115,096 | 161 | 38,016 |
| Nebraska / speeding | 170 | 285 | 380 | 0 | 455 |
| Nebraska / police-reported driver alcohol | 186 | 360 | 289 | 0 | 546 |
| Nebraska / explicit distraction | 40 | 129 | 666 | 0 | 169 |

The total cohorts are **153,273 national fatal crashes** and **835 Nebraska fatal crashes**. Known denominators are yes plus no, so percentages among known cases differ from percentages of all recorded fatal crashes. For example, national explicit distraction is 6,397/38,016 known cases, with 115,096 crashes still unknown. Its known-case fraction cannot be presented as distraction prevalence among drivers, nor even as a fully ascertained fraction of all fatal crashes.

Wilson intervals accompany known-case fractions only. FARS is a census of recorded fatal crashes; those intervals do not capture selective reporting, missingness, police ascertainment, or causal uncertainty. None of these current-event behavior fields enters the prospective safety model.

```bash
.venv/bin/python -m safety.cli --root data/safety behavior \
  --archive-dir /tmp --years 2021 2022 2023 2024
```

## Data needed for a different modeling claim

A driver-behavior or video model would need authorized observations that exist before the prediction horizon, including non-crash driving exposure. The current project has neither first-party telematics nor an agency video agreement. It cannot infer reaction time, distraction propensity, or driver intent from crash coordinates or road imagery.

A concrete next pilot would establish an agency/fleet data agreement, instrumented-vehicle consent and retention rules, then collect time-stamped speed, braking/acceleration, road context, and independently reviewed safety events alongside normal driving. Freeze a prediction horizon and label-maturity policy. Separate entire drivers/vehicles, trips, geography, and later time periods across evaluations; do not let nearby frames or the same trip appear on both sides of a split. Quantify missing sensors, event-selection bias, exposure, and subgroup performance before selecting a model.

For video, require actual rights to the recordings and model weights, a documented privacy/access plan, timestamped labels, and a reviewer-defined task such as detection of road hazards or near-conflicts. A pretrained vision encoder can then be compared with simpler road-feature and temporal baselines on an independent holdout. Its availability or architectural size alone establishes no performance benefit. Foundation-model selection, fine-tuning, and any human-behavior inference remain proposed work requiring those data and evaluations.

Commercial reuse still requires resolving NDOT terms and any new provider agreements. Additional model families cannot substitute for authorized exposure data, leakage-safe validation, a reviewed agency workflow, and demonstrated usefulness.
