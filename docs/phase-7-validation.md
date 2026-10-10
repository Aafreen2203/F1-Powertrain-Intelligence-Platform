# Phase 7: Real-data integration and analytics validation

Validation performed **2026-10-10** (Europe/Dublin). The public session and
synthetic sensor results below are separate data sources and are not combined.

## FastF1 integration

The installed environment reported FastF1 **3.8.3**. Local introspection
confirmed the signatures used by `src/data/fastf1_loader.py`: cache setup via
`Cache.enable_cache`, schedule lookup via `get_event_schedule`, session lookup
via `get_session`, and loading through `Session.load`. The loader's existing
cache directory (`.fastf1-cache`, configurable through `F1_CACHE_DIR`) was
used; no dependency was changed.

The schedule was retrieved on 2026-10-10 and the latest completed event in the
returned schedule was the **2026 Bahrain Grand Prix Race**. The session event
date was **2026-10-04**; the session start was reported as 2026-10-04 07:00 UTC
(15:00 Bahrain local time). `load_session(2026, "Bahrain Grand Prix", "R")`
loaded the session, and FastF1 exposed **22 drivers**, **1,145 lap records**,
and **31 lap columns**. There were 1,043 laps with a `LapTime`; the `LapTime`
range was 98.22–217.87 seconds. `lap_kpis` for BEA returned 53 timed laps,
2 incomplete laps, a 100.366-second best lap, a 104.127-second median, and
18.48195-second sample standard deviation.

FastF1 emitted warnings while loading: it corrected tyre stint information
for multiple drivers, reported race completion time warnings, and reported
incomplete position data for driver IDs 241–243. These are upstream data
quality notices and were not suppressed or repaired by this project.

### Lap and telemetry integrity

The dashboard selects accurate, timed laps without pit-in or pit-out markers
when available. For ALB, the first two fastest eligible laps were lap 31
(102.284 s) and lap 34 (102.613 s). Their telemetry frames contained 790 and
763 rows respectively, with 18 provider columns and no missing values. After
sorting by `Distance`, both distances were monotonic and had no duplicate
values. Their shared observed distance interval was approximately 0.455 to
5,486.224 metres. The dashboard uses distance as the default horizontal axis;
each lap keeps its own provider samples and is plotted against that shared
distance axis. It does not align rows by sample index or interpolate one lap
onto another.

An additional profile of BEA's fastest eligible lap (lap 40, 100.366 s)
contained 765 rows and 18 columns with no missing values or duplicate
records. Date, session time, elapsed time, and distance were monotonic. Signal
ranges included speed 72–318 km/h, RPM 7,035–12,438, gear 1–8, throttle 0–104,
and distance 0.767–5,499.301 m. Sampling was irregular: the median Date
interval was about 0.13 s, with observed intervals from 0.007 to 1.04 s.
Throttle values above 100 and a constant-zero DRS signal were observed as
provided for this lap; they were not normalized or interpreted as faults.

The full lap table has expected sparsity: `LapTime` was missing on 8.91% of
rows, `PitOutTime` and `PitInTime` on 93.62% each, `Deleted` on 100%, and
`TyreLife` on 13.28%. Several sector fields were also partially missing
(approximately 0.26–2.27%). Missing fields are not imputed. The telemetry
quality profile excludes datetime and timedelta columns from numeric signal
statistics. Public FastF1 telemetry is driver/car telemetry, not dedicated
power-unit temperature, pressure, or internal engine-health sensor data; those
channels are unavailable here.

The Streamlit F1 page consumed the loaded session and displayed ALB lap 31
with Speed against Distance, without AppTest exceptions. The app clears
previous schedule/session/telemetry state when a new selection or retrieval
failure makes that state stale.

## Synthetic anomaly evaluation

This evaluation used only the reproducible generated sensor dataset:
`generate_sensor_data(seed=42)` produced **700 rows** with **81 injected
anomaly labels**. The chronological split was at row 489 (428 known-normal
training rows and 211 held-out rows); the held-out set contained 20 known
anomalies. The evaluation function selected four sensor columns as features;
`anomaly_label` was excluded from model input and retained only as the
evaluation target. Training used only known-normal rows from the earlier
segment. This is a clean-normal training assumption, not a claim about
production fleet labels.

| Method | Precision | Recall | F1 | False-positive rate | TP | FP | TN | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Statistical robust-z baseline | 0.00 | 0.00 | 0.000000 | 0.000000 | 0 | 0 | 191 | 20 |
| Isolation Forest | 0.52 | 0.65 | 0.577778 | 0.062827 | 13 | 12 | 179 | 7 |

Precision is the share of flagged rows that were labelled anomalies; recall
is the share of held-out labelled anomalies flagged; F1 is their harmonic
mean; false-positive rate is FP/(FP+TN), or the share of held-out normal rows
flagged. The thresholded robust-z baseline flagged none on this held-out
segment, so its precision is numerically zero when it finds no positives
(rather than evidence that future anomalies will be detected at zero
precision). Metrics depend on the generated event locations, chosen features,
threshold, and one seeded split. These synthetic labels and results do not
measure real engine failures or predict power-unit reliability.

## Dashboard and failure-path checks

Streamlit AppTest checks exercised:

- The F1 telemetry page with the loaded public Bahrain session and ALB data.
- The synthetic anomaly page and model evaluation page.
- Data quality page with public telemetry supplied.
- Engineering reports page, including clicking its three download controls.
- A schedule retrieval exception (`ConnectionError("simulated unavailable network")`): the page showed the unavailable-schedule message, cleared stale schedule data, and raised no AppTest exception.
- A loaded session with an empty lap table: the page showed its no-driver-laps warning and raised no AppTest exception.

The unavailable-network check simulated the exception locally; it was not a
claim that the public service was unavailable during retrieval. The reporting
pipeline was also run against seed 42 and wrote its five expected artifacts
to a temporary directory. No report export or dashboard result was used as
input to model training.

## Commands and verification

The real data path was invoked through the existing loader, equivalent to:

```python
from src.data.fastf1_loader import list_events, load_session

events = list_events(2026)
session = load_session(2026, "Bahrain Grand Prix", "R")
```

The installed API signatures were inspected locally with Python's `inspect`
module. Final local checks for this phase:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app.py src pages tests
```

The final test run completed with **23 passed**; Ruff reported **All checks
passed**; `compileall` completed with no diagnostics; and `pip check` reported
no broken requirements. The README's install command was checked against the
existing environment and requirements files, but a fresh environment install
was not performed. No dependency upgrades were made. No credentials were
required by the integration. The FastF1 cache is local and ignored by version
control.
