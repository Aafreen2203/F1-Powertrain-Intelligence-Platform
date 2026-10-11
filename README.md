# F1 Powertrain Intelligence Platform

An independent motorsport engineering analytics portfolio project built from publicly available Formula 1 session data and clearly labelled synthetic sensor readings. It is not affiliated with Red Bull Racing and does not use or imply access to confidential team or power-unit data.

## Motivation

The project demonstrates a reproducible data workflow relevant to data strategy and engineering insights: sourcing, quality checks, telemetry comparison, anomaly analysis, KPI monitoring, visualisation, and concise reporting. All performance conclusions will be descriptive and tied to the available session context.

## Architecture and data flow

See [docs/architecture.md](docs/architecture.md). Public FastF1 telemetry and synthetic sensor data have separate loaders and analysis paths. Reusable code lives in `src/`; Streamlit pages are a presentation layer; report exports and unit tests are independent of the dashboard.

## Setup

The project configuration targets Python 3.11 or newer; Python 3.11 is the CI version. The local development environment was inspected with Python 3.14.7. Create an isolated environment and install the development dependencies before running tests or the dashboard:

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

Injected event names appear in `event_label`; `anomaly_label` is the known binary ground truth. The DataFrame metadata also identifies it as synthetic. To retrieve public data, use `src.data.fastf1_loader.list_events(...)`, `load_session(...)`, then `load_driver_telemetry(...)`. The first request can be slow. FastF1 caches fetched data in the system temporary directory by default (suitable for hosted ephemeral storage); set `F1_CACHE_DIR` or pass `cache_dir` to override it. Cache contents are disposable and are not committed.

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
- Compare same-event, same-driver laps for Speed, RPM, Throttle, Brake, and gear using circuit distance; raw provider traces remain unmodified and continuous channels are interpolated only for derived differences.
- Validate required schema, missingness, duplicates, numeric ranges, timestamp order, and sampling intervals without mutating the source data.
- Compare a configurable robust statistical baseline with Isolation Forest on a chronologically held-out synthetic sensor set.
- Screen selected real FastF1 laps for contextual potential anomalies with a causal robust baseline or an explicitly in-sample, exploratory Isolation Forest.
- Explore unlabelled real-lap sensitivity to baseline thresholds/windows and Isolation Forest contamination; this is not accuracy validation.

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

Run `python -m streamlit run app.py` to open the overview and sidebar pages: F1 Telemetry Explorer, Telemetry Anomaly Analysis, Synthetic Sensor Lab, Data Quality, Model Evaluation, and Engineering Reports. Load the year, event, and session in F1 Telemetry Explorer first; select a driver, valid reference lap, and comparison laps to inspect raw traces, distance-aligned differences, lap conditions, and evidence-backed interpretations. The reload button reissues the loader call; FastF1 may use its cache. The UI labels call-completion time separately from cache/network origin, which remains unknown because the loader cannot reliably identify it. Telemetry availability, sample count, channels, lap quality, and alignment coverage are displayed. Real telemetry anomaly and comparison CSVs plus labelled Markdown reports are downloadable in memory. Synthetic sensor summaries and labelled benchmark metrics remain a separate workflow. The real workflow does not substitute simulated data when session loading fails.

## Deployment and CI

The Streamlit Community Cloud entry point is the repository-root `app.py`; `requirements.txt` is the authoritative runtime dependency list used by Community Cloud. `pyproject.toml` configures Ruff and pytest and does not declare runtime dependencies. No secrets or external services are required for the current public-data workflow. Community Cloud can retrieve FastF1 data only when its network and the upstream service are available; the app shows retrieval failures and keeps synthetic demonstrations separate. See [deployment and developer workflow](docs/deployment.md) for exact setup steps. GitHub Actions runs tests and quality checks; Streamlit Community Cloud's GitHub integration handles deployment after changes are merged into `main`.

The principal question is how a driver's speed and RPM behaviour varies across comparable laps and which deviations merit further investigation. Public telemetry differences can reflect braking, acceleration, shifting, tyres, weather, traffic, setup, and track evolution. They do not establish internal power-unit health. FastF1 does not expose the full internal sensors a powertrain team may use, and the synthetic temperature, pressure, vibration, and RPM channels are simulated. See [Phase 8 validation and methodology](docs/phase-8-validation.md) for the distance alignment, limitations, actual cached-session results, and checks performed.

See [docs/real-telemetry-anomaly-analysis.md](docs/real-telemetry-anomaly-analysis.md) for channel preparation, causal feature construction, methods, scoring limits, and exports. Public FastF1 telemetry is unlabelled and is not internal power-unit instrumentation: no real-world precision/recall/F1 or engine-failure prediction claims are made.

## Current status

Phase 9 adds explicit lap eligibility reasons, nearest lap-midpoint weather context, per-channel alignment coverage, unit-aware anomaly explanations, and a reportable comparison case study. See [docs/phase-9-validation.md](docs/phase-9-validation.md) for actual cached-session observations, validation commands, and limitations, and [docs/fastf1-retrieval-validation.md](docs/fastf1-retrieval-validation.md) for the production retrieval diagnostics, live-data validation, and Cloud verification steps. Automated tests use local fixtures/mocks and do not require live data access. Python 3.14.7 is the locally inspected runtime; CI targets the declared minimum Python 3.11.
