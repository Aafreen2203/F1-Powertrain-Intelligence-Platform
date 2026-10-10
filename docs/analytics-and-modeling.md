# Phase 3–4: validation, analytics, and anomaly evaluation

## Data quality

`src.validation.validate_frame` produces record and column counts, missing counts and percentages, observed dtypes, optional expected-type checks, duplicate-record counts, optional numeric range violations, timestamp parse/order/duplicate checks, and sampling-interval warnings. Required-schema, type mismatches, and invalid-value conditions are failures; missingness, duplicates, and timing irregularities are warnings. The check is non-destructive: it does not sort, drop, or impute rows. This is a report of structural quality, not proof that values are physically plausible.

## Public telemetry analytics

`telemetry_profile` discovers numeric channels from the frame at runtime and summarizes only those columns. Its correlation matrix is exploratory and does not establish causality. `lap_kpis` reports timed and incomplete lap counts plus best, median, and sample standard deviation of lap times by a chosen grouping column. It excludes only missing/unparseable lap times from timing statistics and reports their count. Driver comparisons are descriptive: weather, traffic, car setup, track evolution, tyre state, and other context are not controlled for.

## Synthetic sensor benchmark

`evaluate_anomaly_methods` preserves the input row order and splits chronologically. The later block is held out. Within the earlier block, injected labels are used to select known-normal rows for fitting; labels are never model features, and test labels are used only to calculate evaluation metrics. This is a labelled synthetic, semi-supervised benchmark with a clean-normal training set, not a fully unsupervised field deployment simulation. In an operational unlabeled context, this clean training subset assumption would need a separately justified baseline period or contamination-tolerant training strategy.

The statistical baseline computes each signal's training median and robust scale (`1.4826 × MAD`; standard deviation is a fallback when MAD is zero). A held-out row is flagged if any feature's absolute robust z-score exceeds the configurable threshold (default 3.5). Its explanation names the signal and z-score. It is transparent but assumes a mostly stable distribution and may miss multivariate, gradual, or context-dependent changes.

Isolation Forest is fitted only on the same earlier known-normal feature rows. Its `contamination` parameter controls the estimated training outlier fraction used to set a decision boundary; it is not an estimated real fault prevalence. Anomaly scores and a generic boundary explanation are returned. Inspect the signal values and baseline deviations before interpreting a flag.

## Evaluation metrics

Metrics are calculated on the held-out later block, with an injected anomaly as the positive class:

- **Precision** = TP / (TP + FP): fraction of flagged records that have an injected label. Low precision means more false alarms.
- **Recall** = TP / (TP + FN): fraction of injected anomaly records that were flagged. Low recall means more missed injected records.
- **F1** = harmonic mean of precision and recall. It is zero when there are no true positives and balances those two rates; it does not account for the relative cost of misses versus false alarms.
- **False-positive rate (FPR)** = FP / (FP + TN): fraction of known-normal held-out records incorrectly flagged. It can be undefined (reported NaN) if a test block contains no normal records.
- **TP, FP, TN, FN** are the raw confusion-matrix counts, useful for understanding the sample size behind rates.

No metric is hardcoded. Results depend on the seed, injected event design, selected features, time split, baseline threshold, and Isolation Forest contamination setting. The anomaly label marks generated scenarios; detection is not diagnosis, failure prediction, or a claim about genuine power-unit behaviour. There is no validated real failure data here.

## Real FastF1 telemetry review

`src.analytics.telemetry_anomaly.analyze_telemetry` analyzes a selected public lap using available Speed, RPM, Throttle, Brake, and gear channels and requires Distance. It counts and explicitly handles invalid distances, duplicate distances (stable-sort and keep the last provider sample), nonfinite signals, unavailable/constant channels, and samples with no usable signal. It does not impute values. The statistical baseline scores causal robust deviations from preceding samples for Speed/RPM/Throttle levels and changes. When local MAD is tiny, it falls back to preceding-window standard deviation and a 1% underlying-channel scale floor with signal-specific minimums. Brake state and gear are context rather than direct anomaly features; Speed/Throttle levels and changes are masked at braking samples and the following sample, while RPM level/change scores are masked around gear changes. The configurable threshold marks potential anomalies for contextual review.

The optional Isolation Forest uses available levels and derived changes, a configured contamination fraction, and a fixed random seed. It is fit and scored on the same selected unlabelled lap. This exploratory in-sample method is not a holdout evaluation. Public FastF1 data has no verified anomaly labels in this application, so real telemetry produces counts, scores, segments, and quality summaries only—not precision, recall, F1, accuracy, false-positive rates, confirmed fault labels, or failure predictions. See [real-telemetry-anomaly-analysis.md](real-telemetry-anomaly-analysis.md) for full feature and interpretation details.

`sensitivity_analysis` rescans the selected lap at several fixed statistical thresholds and preceding-window sizes and Isolation Forest contamination settings. It reports actual flag/segment counts and whether a segment center recurs within 100 m under another setting of the same method. That distance is a descriptive UI heuristic, not a validated tolerance. This view is explicitly sensitivity analysis, not accuracy validation; no labels are accepted by the function and no real-data model performance metrics are calculated.

`align_laps_by_distance` compares same-driver laps on the shared circuit-distance interval, never by row index. Continuous channels and Time are linearly interpolated between adjacent finite provider samples on a 5 m grid; missing gaps are not bridged and there is no extrapolation. Brake and gear use nearest-sample context. The comparison sign is comparison minus reference. Original provider samples remain available for raw plots. Interpolation may smooth transients and cannot control for lap context.

## Run checks

```bash
source .venv/bin/activate
pytest -q
```
