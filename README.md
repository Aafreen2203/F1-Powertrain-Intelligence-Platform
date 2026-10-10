# F1 Powertrain Intelligence Platform

An independent motorsport engineering analytics portfolio project built from publicly available Formula 1 session data and clearly labelled synthetic sensor readings. It is not affiliated with Red Bull Racing and does not use or imply access to confidential team or power-unit data.

## Motivation

The project demonstrates a reproducible data workflow relevant to data strategy and engineering insights: sourcing, quality checks, telemetry comparison, anomaly analysis, KPI monitoring, visualisation, and concise reporting. All performance conclusions will be descriptive and tied to the available session context.

## Architecture and data flow

See [docs/architecture.md](docs/architecture.md). Public FastF1 telemetry and synthetic sensor data have separate loaders and analysis paths. Reusable code lives in `src/`; Streamlit pages are a presentation layer; report exports and unit tests are independent of the dashboard.

## Setup

The current local environment uses Python 3.14.7. The dependency file declares Python 3.11+ as its intended range, but not every supported minor version has been verified. Create an isolated environment and install the full dependency set before running tests or the dashboard:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

Generate a labelled sample without contacting the F1 data service:

```python
from src.data.synthetic_sensors import generate_sensor_data

sensors = generate_sensor_data(n_samples=700, seed=42)
print(sensors.head())
```

Injected event names appear in `event_label`; `anomaly_label` is the known binary ground truth. The DataFrame metadata also identifies it as synthetic. To retrieve public data, use `src.data.fastf1_loader.list_events(...)`, `load_session(...)`, then `load_driver_telemetry(...)`. The first request can be slow; FastF1 caches fetched data under `.fastf1-cache/` by default. Set `F1_CACHE_DIR` or pass `cache_dir` to change that local path.

Run the reusable pipeline without Streamlit to validate the synthetic data, calculate sensor summaries, evaluate both anomaly methods, and export timestamped CSV, interactive HTML, and Markdown artifacts under `reports/`:

```python
from src.reporting import run_synthetic_pipeline

result = run_synthetic_pipeline(seed=42)
print(result.artifacts)
```

## Data sources and limitations

FastF1 provides access to public F1 timing and telemetry data where available. Retrieval requires network access and depends on event/session availability. The loader enables FastF1 caching, inspects available signals, and reports gaps rather than fabricating values. FastF1 and upstream data provider terms apply; review their current terms and attribution guidance before redistributing retrieved data. This project does not bundle or redistribute raw telemetry.

Simulated temperature, pressure, vibration, and rotational-speed channels are illustrative only. They are not actual F1 power-unit measurements. Injected anomaly labels describe generated scenarios, not real engine failures.

## Implemented analysis

- Inspect available telemetry columns and calculate descriptive profiles and lap KPIs.
- Validate required schema, missingness, duplicates, numeric ranges, timestamp order, and sampling intervals without mutating the source data.
- Compare a configurable robust statistical baseline with Isolation Forest on a chronologically held-out synthetic sensor set.
- Screen selected real FastF1 laps for contextual potential anomalies with a causal robust baseline or an explicitly in-sample, exploratory Isolation Forest.

Metric definitions, fitting protocol, assumptions, and limitations are described in [docs/analytics-and-modeling.md](docs/analytics-and-modeling.md).

## Tests

Run the deterministic test suite with:

```bash
python -m pytest
ruff check .
```

Unit tests will not require live internet access.

## Screenshots

Screenshots can be added under `docs/screenshots/`.

## Dashboard

Run `python -m streamlit run app.py` to open the overview and sidebar pages: F1 Telemetry Explorer, Telemetry Anomaly Analysis, Synthetic Sensor Lab, Data Quality, Model Evaluation, and Engineering Reports. Load the year, event, and session in F1 Telemetry Explorer first; select driver/lap and inspect potential anomalies in Telemetry Anomaly Analysis. Real telemetry anomaly and quality CSVs plus an interpretation-labelled Markdown report can be downloaded from the analysis and Engineering Reports pages. Synthetic sensor summaries and labelled benchmark metrics remain a separate workflow. The real workflow does not substitute simulated data when session loading fails.

See [docs/real-telemetry-anomaly-analysis.md](docs/real-telemetry-anomaly-analysis.md) for channel preparation, causal feature construction, methods, scoring limits, and exports. Public FastF1 telemetry is unlabelled and is not internal power-unit instrumentation: no real-world precision/recall/F1 or engine-failure prediction claims are made.

## Current status

Phases 1–7 established the public-data integration and synthetic benchmark; the real telemetry anomaly workflow is described above. The Phase 7 integration check retrieved the 2026 Bahrain Grand Prix Race using FastF1 3.8.3 on 2026-10-10; see [docs/phase-7-validation.md](docs/phase-7-validation.md) for the observed session data and limitations. Automated tests use local fixtures/mocks and do not require live data access. Python 3.14.7 is the locally inspected runtime; the declared Python 3.11+ range has not been verified on every minor version.
