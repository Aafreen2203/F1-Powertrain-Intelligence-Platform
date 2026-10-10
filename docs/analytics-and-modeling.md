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

## Run checks

```bash
source .venv/bin/activate
pytest -q
```
