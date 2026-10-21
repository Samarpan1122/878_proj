# Omaha study: corrected evaluation and measured results

The original Omaha results need better evaluation and adaptation to reporting drift. Adding model complexity alone does not resolve sparse classes, changing data sources, or inconsistent feature availability. This continuation preserves the four-class task, corrects GIS counting, separates frozen prediction from monthly updating, and retains original artifacts.

This is the **noncommercial research dataset**, separate from the official FARS/NDOT safety engine. Severity classes 1–4 describe reported traffic impact, not KABCO injury severity. Duration is the recorded interval between incident start and end, not measured driver delay or independently verified road clearance time. These models do not establish human behavioral causes.

## Population and original split

The cache contains **26,480 incidents at 8,745 rounded locations**: 26,192 in the Omaha–Council Bluffs area and 288 in Lincoln. There are 25,225 Nebraska and 1,255 Iowa records. “Omaha” is shorthand for this combined study scope.

| Partition | Rows | First incident start | Last incident start |
|---|---:|---|---|
| Original first 80% | 21,184 | 2016-03-23 07:55:12 | 2019-12-15 12:39:01 |
| Original final 20% | 5,296 | 2019-12-15 12:45:00 | 2023-03-27 13:44:30 |

Corrected fits exclude outcomes whose `End_Time` has not passed at the prediction boundary. Original test identities remain fixed. Four original training records end at or after the first test origin; the monthly experiment initially trains on 21,180 completed incidents. The cleaned table has no missing severity or duration labels.

| Traffic-impact class | Original training support | Original test support |
|---|---:|---:|
| 1 | 12 | 79 |
| 2 | 17,574 | 4,262 |
| 3 | 3,497 | 839 |
| 4 | 101 | 116 |

Class 1 is especially scarce in training; class 4 is also uncommon. Neither high overall accuracy nor binary severe-versus-not performance establishes useful performance across all four classes. New comparisons retain every class and disclose class support and recall.

Negative log-R² means greater squared error on `log(1 + duration)` than a constant equal to the **test period's mean log-duration**. That mean was unavailable beforehand. Compare training-only and rolling baselines as well: negative R² signals limited fit, but does not by itself show that a deployable prior-data baseline was better.

## Measured data shifts

Source1's share rises from **4.87% of training records to 40.75% of test records**. Overall median duration rises from **30.08 to 60.34 minutes**, and mean duration from **53.62 to 96.70 minutes**. Within Source2, median duration rises from 30.00 to 59.82 minutes; within Source1 it falls from 360.00 to 77.71 minutes. These are measured reporting shifts, not identified changes in crash mechanics.

Precipitation is missing in **78.70% of training records versus 0.04% of test records**. Across the whole cache, speed-limit data is missing in 29.72% and lane count in 16.87%. Models may learn recording practices as well as roadway associations.

Imagery is complete numerically, but 22,389 records use 2022 NAIP imagery and 4,091 use 2023 imagery. **25,511 records, or 96.34%, have imagery from a later calendar year than the incident; this includes every original training record.** Same-year imagery is not necessarily pre-incident either. These are retrospective geographic features, not demonstrated historical forecasting inputs. ImageNet ResNet-18 embeddings and NDVI thresholds are not a road-safety foundation model or validated semantic segmentation.

[data_audit.json](../outputs/research/metro/data_audit.json) records aggregate values, input hashes, exact split dates and exploratory baselines without exposing individual records.

## GIS and validation corrections

Original road density counted both directions of many OSM drive-graph edges. The correction deduplicates exact normalized centerline geometries before clipping length to 100, 250 and 500 metre buffers. Parallel carriageways remain distinct. This is exact geometry deduplication, not a topological union or grade-separation inference.

Omaha's 99,150 graph edges contain 43,211 repeated geometries; Lincoln's 32,873 contain 14,082. Total directed-edge length is approximately 1.785 and 1.779 times deduplicated length, respectively. Local corrections vary rather than applying a blanket multiplier.

| Feature | Original mean | Corrected mean | Changed rows |
|---|---:|---:|---:|
| `road_km_per_km2_100` | 30.0911 | 24.3658 | 16,949 |
| `road_km_per_km2_250` | 22.3779 | 15.9320 | 25,024 |
| `road_km_per_km2_500` | 20.1585 | 12.9049 | 26,389 |

[metro_features_corrected.parquet](../outputs/research/metro/metro_features_corrected.parquet) preserves all 26,480 row identities and their order. **Every other column is unchanged**, including imagery, targets, other GIS fields and archived neighborhood columns. Original caches were not overwritten. [gis_correction.json](../outputs/research/metro/gis_correction.json) records source/OSM/output hashes and preservation checks. Four geometry and cache-preservation tests passed.

The neighborhood defect is separate. In original five-fold spatial CV, **6,045–8,565 training rows per fold used outcome information from held-out records**. The archived E spatial-neighborhood scores therefore do not establish independent spatial generalization. This defect does not, by itself, invalidate neighbor-free A–D rows. In the original temporal test, 4,988 of 5,296 rows use earlier test outcomes in their history: that can describe an online process, but not a frozen training-only holdout.

`src/metro_challengers.py` rebuilds history from the fit partition, requires referenced incidents to have ended before each query, fits preprocessing/PCA on training data, and disables random internal early stopping with `early_stopping=False`. The corrected parquet still contains archived history columns; use the corrected benchmark's history construction rather than those cached values.

The new spatial-forward protocol holds out later incidents in unseen geographic cells. It is unbuffered and **differs from original all-time five-fold spatial CV**. “Original” recipe rows in the new benchmark mean matched legacy recipes with corrected boundaries, preprocessing and GIS; they need not reproduce archived scores exactly.

## Monthly adaptation: completed experiment

[online.json](../outputs/research/metro/online.json) scores the same 5,296 original test incidents across 40 periods. The fixed comparator trains once before the first origin. The monthly variant retrains only on incidents whose `End_Time` precedes each month's origin. It legitimately receives earlier completed test-period outcomes as time advances, a different information set from frozen prediction.

Both use the same tabular/location recipe, 150 boosting iterations and fixed 180-day recency half-life; classification weights are normalized within each training class. They use no GIS, imagery, cached neighborhood outcomes, or observed Severity as a duration predictor. Original paper duration ablations and default frozen challengers condition on observed Severity, so their scores answer a different question.

| Metric | Matched fixed model | Monthly completed-label updates |
|---|---:|---:|
| Four-class balanced accuracy | 0.46474 | 0.46814 |
| Four-class macro F1 | 0.40356 | 0.43734 |
| Accuracy | 0.76813 | 0.81552 |
| Duration MAE, minutes | 55.3352 | 53.4041 |
| Duration RMSE, minutes | 217.5940 | 212.2637 |
| Duration log-R² | −0.01441 | 0.09906 |

Duration MAE falls **1.9311 minutes**, about 3.49%, against the matched fixed model. The exploratory 95% geographic-block interval is **1.1008 to 2.8262 minutes**. The balanced-accuracy difference interval is **−0.02285 to 0.02960** and includes zero. Intervals condition on fitted models, are not selection-adjusted, and exclude temporal dependence and model-refitting uncertainty. No corresponding confidence claim is made for macro F1.

Rare-class behavior remains weak: monthly class-1 recall is 6.33% and class-4 recall 12.07%; fixed class-4 recall is 29.31%. Aggregate gains must not hide that regression. The rolling mean-log duration baseline has MAE 55.0495 minutes and log-R² −0.02191. Positive log-R² of 0.09906 is an improvement, not a high-accuracy duration model.

Prediction artifacts include incident IDs and the exact test-ID hash. The original input was revalidated for chronology, identity and target consistency after the run without changing predictions or metrics. [online_verification.json](../outputs/research/metro/online_verification.json) passed: all 12 saved metric values were independently recalculated across 5,296 prediction rows, and the final saved monthly model reproduced its eight original evaluation rows. Earlier monthly models were not retained; this does not claim they were independently reloaded. Targeted checks passed: 17 API, six online, four GIS and 12 frozen-challenger tests, 39 in total. Browser checks passed both frozen protocols, both duration objectives, monthly evaluation and error recovery at 1440px/390px, with no JavaScript errors or viewport overflow; independent Omaha finish review disposition: SHIP.

The corpus and original holdout were already inspected. This is a development experiment, not independent validation or a live trial. Recorded weather/road flags also lack a complete availability audit.

## Frozen corrected challengers

Both protocols are complete in [benchmark.json](../outputs/research/metro/benchmark.json). Every arrow below compares a corrected matched legacy recipe with its inner-validation-selected challenger on the same outer records. This is not a comparison against archived scores or monthly adaptation.

Temporal fitting uses 16,946 inner-training, 4,233 validation and 21,180 outer-training records; testing retains all 5,296 original test incidents. Classification selects `regularized_balanced_hgb` with inner-only decision calibration.

| Feature set | Balanced accuracy | Macro F1 | Duration MAE, minutes | Duration log-R² |
|---|---:|---:|---:|---:|
| A: tabular | 0.32417 → 0.48250 | 0.32154 → 0.26853 | 57.9188 → 54.3557 | −0.26974 → −0.01326 |
| B: tabular + GIS | 0.43516 → 0.52241 | 0.42442 → 0.37562 | 58.1309 → 54.3557 | −0.30054 → −0.01326 |
| C: imagery | 0.36586 → 0.37746 | 0.32993 → 0.27573 | 66.5433 → 54.3992 | −0.39399 → −0.01539 |
| D: tabular + GIS + imagery | 0.43014 → 0.51633 | 0.42164 → 0.37698 | 58.3202 → 54.3557 | −0.32392 → −0.01326 |
| E: D + corrected history | 0.43667 → 0.52183 | 0.42431 → 0.37518 | 58.3871 → 54.3557 | −0.32509 → −0.01326 |

**This is a classification tradeoff, not an overall improvement.** Temporal balanced accuracy increases, but macro F1 falls in every feature set. For B, exploratory paired 95% intervals are [0.06345, 0.11098] for balanced-accuracy change and [−0.06449, −0.02781] for macro-F1 change. The imagery-only balanced-accuracy interval includes zero.

The spatial-forward experiment uses 9,763 inner-training, 979 validation and 16,641 outer-training records. Its **927 later, unseen-cell test records** contain class supports 15/704/194/14. Classification selects `regularized_hgb`, rather than the temporal recipe.

| Feature set | Balanced accuracy | Macro F1 | Duration MAE, minutes | Duration log-R² |
|---|---:|---:|---:|---:|
| A: tabular | 0.29803 → 0.44222 | 0.29768 → 0.29681 | 65.6680 → 62.2006 | −0.27763 → −0.02981 |
| B: tabular + GIS | 0.40015 → 0.47349 | 0.38294 → 0.40870 | 65.1061 → 62.2006 | −0.22627 → −0.02981 |
| C: imagery | 0.36301 → 0.31448 | 0.34336 → 0.27672 | 70.4319 → 62.0213 | −0.23833 → −0.01587 |
| D: tabular + GIS + imagery | 0.40592 → 0.39948 | 0.38816 → 0.34680 | 65.2744 → 62.2006 | −0.20000 → −0.02981 |
| E: D + corrected history | 0.41661 → 0.39357 | 0.40714 → 0.34192 | 64.9654 → 62.2006 | −0.19110 → −0.02981 |

Spatial B improves both classification point estimates, but its exploratory intervals include zero: balanced accuracy [−0.00873, 0.14416], macro F1 [−0.00040, 0.05342]. C, D and E lose on both classification metrics. Extra imagery/history does not establish a generalization gain here.

**The duration winner is a simple recent baseline.** Both MAE and log-MSE selection give `recent_source_median` full weight and `training_mean` zero weight in all ten evaluations. The recipe uses a trailing 365-day fit window and source-specific median log-duration. Imagery-only C has no Source predictor and correctly falls back to the global recent median. Identical A/B/D/E duration results therefore do not show a GIS/imagery contribution, and this is not a deep-model breakthrough. Frozen log-R² remains negative. MAE and log-MSE were selected separately; their selected mixtures happen to coincide in this run.

For B, the duration-MAE reduction interval is [3.2783, 4.2400] minutes temporally and [1.9192, 3.7535] minutes spatially. Frozen intervals use 200 geographic-block draws and are exploratory per-comparison intervals, not familywise or model-selection-adjusted confidence statements. The test corpus was previously examined.

Model choices, preprocessing, calibration and blending remain confined to inner fitting/validation. Duration evaluation here explicitly permits observed Severity; `--duration-context start_context` defines a separate task and was not part of these ten runs. No challenger is promoted into the official-source safety engine.

[inference_verification.json](../outputs/research/metro/inference_verification.json) passed all ten saved-model replays and 12 metric values per artifact: 5,296 rows for each temporal feature set and 927 for each spatial-forward set. The 39 targeted tests and online replay also passed. Final Omaha browser checks passed at 1440px/390px, including both frozen protocols, both duration objectives, monthly evaluation and error recovery; no JavaScript errors or viewport overflow. Independent finish review disposition: SHIP.

## Reproduce locally

Run substantial jobs **sequentially**, from the repository root with the existing research environment. These commands use local caches without downloading imagery or OSM data.

```bash
# Correct three density columns; preserve source caches and write the GIS audit.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -c 'from src.gis import correct_cached_road_density; correct_cached_road_density()'

# Frozen A–E benchmark: Severity explicitly available for duration prediction.
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv/bin/python -m src.metro_challengers \
  --input outputs/research/metro/metro_features_corrected.parquet \
  --output outputs/research/metro/benchmark.json \
  --protocol both --duration-context severity_known --threads 2

# Separate monthly experiment without imagery/GIS or observed Severity input.
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv/bin/python -m src.metro_online \
  --input data/processed/metro_features.parquet \
  --output outputs/research/metro/online.json \
  --iterations 150 --bootstrap-draws 500 --threads 2

.venv/bin/python -m pytest \
  tests/test_metro_gis.py tests/test_metro_challengers.py tests/test_metro_online.py -q
```

Original feature-table SHA256: `137de3245e19c6af2c9589821025ff0d802528c9f5118dde7a676030aab986c4`.
Corrected feature-table SHA256: `ceb6d8a77ee4f115eefed63cb84567c21d6aa9f0c32101940649e01ca299b4ac`.
The unchanged [original ablation CSV](../outputs/tables/metro_ablation.csv) remains an archive, not the corrected leaderboard.

Agency utility and operational injury-risk prediction require appropriate data rights, labels, prospective validation and a real pilot. These research improvements do not establish those outcomes or acquisition readiness.
