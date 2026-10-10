# Architecture proposal

## Design

Keep public FastF1 telemetry and simulated sensor measurements in separate paths and modules. The Streamlit UI is a thin client over reusable `src` components; pipeline/report code must also run without Streamlit.

```text
FastF1 public API -> cache -> telemetry loader -> validation -> distance-aligned lap comparisons -> dashboard/reports
Loaded FastF1 session -> selected lap -> causal contextual scoring / optional exploratory Isolation Forest -> flagged sample review + sensitivity analysis + explicit download exports
Synthetic generator -> labelled sensor frames -> validation -> baseline + Isolation Forest -> dashboard/reports
```

- `src/data/`: FastF1 session retrieval, cache configuration, and seeded synthetic generation.
- `src/validation/`: schema, ranges, timestamps, duplicates, missingness, and quality summaries.
- `src/analytics/`: telemetry profiles, distance-aligned lap comparisons, descriptive KPIs, unlabelled per-lap anomaly screening, and sensitivity analysis.
- `src/models/`: transparent thresholds, time-aware split/evaluation, and Isolation Forest.
- `src/reporting/`: standalone synthetic pipeline plus separate, in-memory real telemetry export builders.
- `pages/`: Streamlit views; `app.py` provides overview and navigation.
- `tests/`: deterministic unit tests, with no network dependency.

## Key decisions

1. Treat the source type as part of each dataset's metadata and user-facing presentation. Never impute or synthesize real telemetry; missing channels remain missing and are reported.
2. Keep downloads and generated outputs out of version control. FastF1 cache location is configurable and defaults to a local ignored directory.
3. Split synthetic records in time before fitting/evaluating anomaly models, and keep injected labels out of model features. In the labelled synthetic benchmark, labels select normal rows in the earlier training block and evaluate the later holdout.
4. Define performance KPIs as descriptive comparisons, with session, driver, lap, and conditions attached. Avoid causal claims from observational data.
5. Keep computations callable outside Streamlit; `src/reporting/pipeline.py` provides the standalone synthetic validation, evaluation, and export workflow.
6. Treat real telemetry flags as exploratory review markers. The causal robust baseline uses preceding samples only; Isolation Forest is fit and scored on the selected unlabelled lap and is not out-of-sample evaluation.
7. Preserve original provider lap samples for plotting. Calculate cross-lap differences only after distance alignment; report comparison-minus-reference sign convention and interpolation limitations.
8. Report retrieval success time and available data in the UI, but mark cache/network provenance unknown unless the FastF1 API provides reliable evidence.

## Data flow and boundaries

Telemetry retrieval returns provider data with available columns inspected at runtime. General validation reports defects and warnings without mutating its input. For anomaly scoring, the telemetry analysis module deliberately sorts by numeric Distance, excludes invalid distances, keeps the last provider sample for duplicate distances, and counts these actions; it never fabricates or imputes values. Synthetic generation creates a separately labelled dataset and known event intervals. Both sources can feed quality reporting, but synthetic anomaly modeling never trains on telemetry and telemetry is never presented as simulated sensor data.
