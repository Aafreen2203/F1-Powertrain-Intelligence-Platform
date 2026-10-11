# Phase 8: Engineering-driven telemetry intelligence

## Engineering question and interpretation

The dashboard asks: **How does a driver's speed and RPM behaviour vary across
comparable laps, and which deviations deserve further engineering
investigation?** The F1 Telemetry Explorer selects a season, event, session,
driver, reference lap, and one or more comparison laps from the same loaded
session. It shows the original provider samples for Speed, RPM, Throttle, Brake,
and gear when those channels are available, followed by aligned Speed/RPM
deltas, a largest-difference table, and a concise calculated interpretation.

The delta sign is **comparison minus reference**. A positive Speed delta means
the comparison lap's sampled/interpolated speed is higher at that location;
the value is not a lap-time gain. The interpretation uses the actual selected
values, aligned distance, interpolated time where available, and brake/gear
signals where both laps provide them. It suggests follow-up checks but does not
claim a mechanical cause.

## Alignment method

`src.analytics.lap_comparison.align_laps_by_distance` copies each input and
requires `Distance`. It converts distance numerically, removes invalid
distances, stable-sorts, and keeps the last sample at duplicate distances. It
uses a 5 m circuit-distance grid over the shared distance interval by default.
Speed, RPM, Throttle, and Time are linearly interpolated only between adjacent
finite source samples; missing runs are not bridged and values are not
extrapolated beyond finite neighbours. Brake and `nGear` use the nearest source
sample, preserving discrete states. Derived deltas are computed only for
channels provided by both laps. Original provider samples are plotted
separately, unmodified, so short transients remain inspectable. Interpolation
can smooth brief changes and a distance-matched pair is not a causal control:
tyres, weather, traffic, setup, track evolution, driver inputs, and session
context may differ.

The anomaly page remains a single-lap screening workflow. Each flagged sample
includes the selected feature, observed feature value, preceding-window local
median, score, explanation, time/distance, and available brake/gear context.
Brake and gear are context only, not Isolation Forest or statistical model
features. A code review in Phase 8 also corrected gear leakage into the
statistical feature matrix. Isolation Forest is still fit and scored on that
same unlabelled lap; no out-of-sample real-data metrics are calculated.

Sensitivity analysis rescans one public lap at baseline thresholds 4/6/8 and
three windows (approximately half, the selected window, and double the
selected window), and at Isolation Forest contamination settings 0.01/0.03/0.08
with the selected window. Its “region reappears” column means at least one
segment center is within 100 m of a segment under another setting of the same
method. This is a descriptive stability indicator, not accuracy validation,
ground truth, or a validated engineering tolerance. Random state is fixed at
42 in the dashboard. Extra fits run only after the reviewer presses the
sensitivity button; normal page load does not repeat them.

## Retrieval diagnostics

The flow remains `list_events` → `load_session` → `list_drivers` →
`load_driver_telemetry` → distance alignment or analysis → dashboard/export.
At the time of this Phase 8 validation, the local cache was explicitly set to
`.fastf1-cache`; the current default is the system temporary directory, with
`F1_CACHE_DIR` and `cache_dir` overrides. The app provides
an explicit load/reload button, a UTC timestamp for when the load call returned,
selected driver/lap, sample count, available channel list, and quality validation. The
loader does not expose reliable cache-hit versus network-fetch provenance, so
the UI labels that origin **unknown** rather than calling cached data live or
claiming a network request. Failed and partial data states are shown; no
synthetic fallback is used. Partial telemetry without Distance can still be
inspected on its own sample axis, but comparisons are disabled rather than
row-aligned.

## Public telemetry limits

FastF1 public racing telemetry can contain Speed, RPM, Throttle, Brake, and
gear, depending on session and lap. It does not provide the complete internal
power-unit sensor suite used by an F1 engineering team. Public data can support
driving-performance and telemetry-pattern analysis; it cannot independently
establish engine health or confirm a power-unit failure. Unusual behaviour can
be normal driving, circuit, weather, tyre, traffic, session, or data-provider
variation. Synthetic temperature, pressure, vibration, and RPM are generated
signals and are kept on their separate labelled workflow. Stronger conclusions
would require verified fault labels, suitable reference measurements,
engineering context, and authorised internal sensor data. No confidential
team systems or data are used.

## Actual data check

Validation on **2026-10-10** used the installed FastF1 **3.8.3** and the
existing local cache. The exact request was
`load_session(2026, "Bahrain Grand Prix", "R", cache_dir=".fastf1-cache")`.
FastF1 logs explicitly reported `Using cached data` for session info, driver
info, session status, lap count, track status, extended timing, timing app,
car, position, and weather data. This was a **successful cached retrieval**;
no uncached network request was performed in this Phase 8 check. FastF1
returned 22 drivers and 1,145 lap records. It emitted tyre-stint correction
and race-completion warnings, which remain upstream data-quality notices.
Local signature inspection confirmed that installed FastF1 3.8.3 exposes the
loader-used `Cache.enable_cache`, `get_event_schedule`, `get_session`, and
`Session.load` APIs with the keyword arguments used by the existing loader.

Selected comparison: **2026 Bahrain Grand Prix Race, ALB, lap 31 reference vs
lap 34 comparison**. Lap 31 contained 790 rows and lap 34 763 rows; both had 18
provider columns. Each frame had zero missing values, strictly increasing
Date and Distance, and zero duplicate Distance values. Both supplied Speed,
RPM, Throttle, Brake, nGear, Time, and Date. Observed ranges:

- Lap 31: Speed 72–311 km/h; RPM 8,132–12,164; Throttle 0–100; Brake 0–1;
  gear 1–8; Distance 0.455–5,495.050 m.
- Lap 34: Speed 70–312 km/h; RPM 7,976–12,096; Throttle 0–100; Brake 0–1;
  gear 1–8; Distance 0.044–5,486.224 m.
- Median sample interval by Date was 0.13 s on both laps. Their shared
  distance interval was 0.455–5,486.224 m, producing 1,099 grid points at
  approximately 5 m spacing.

Largest absolute channel differences from the computed comparison table:

| Channel | Distance | Reference | Comparison | Comparison minus reference | Mean absolute difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| Speed | 4,195.5 m | 186.1 km/h | 152.8 km/h | -33.4 km/h | 6.37 km/h |
| RPM | 1,930.5 m | 8,684.8 | 10,919.2 | +2,234.4 | 401.72 |
| Throttle | 4,500.5 m | 100.0% | 14.5% | -85.5 percentage points | 5.00 percentage points |

At the largest Speed difference, both brake samples were active; reference
gear was 7 and comparison gear was 6. The interpolated within-lap times at
that location were 74.27 s and 74.71 s. This makes braking/gear context a
plausible part of the observed difference, not proof of why it happened. It
does not establish a power-unit concern. The next useful checks are raw traces,
sector and tyre/weather context, and suitable authorised engineering
measurements.

For ALB lap 31, the default statistical baseline (threshold 6, window 31)
scored 790 samples, flagged 12 samples in 10 contiguous segments, and reported
Speed, RPM, and Throttle as available scoring signals with Brake and gear as
context only. This is unlabelled screening, not performance evaluation.

The F1 Telemetry Explorer was run under AppTest with the actual cached session
preloaded. It raised no app exceptions, rendered six Plotly charts, and
produced the Engineering Interpretation. The Telemetry Anomaly Analysis page
was separately run with the actual cached session; its default widgets
selected ALB lap 3, rendered five charts and all three downloads, and raised
no app exceptions. Pressing **Run sensitivity analysis** completed without
exceptions and displayed the tables. These runs reused FastF1 cached inputs;
they did not make an uncached network request.

Sensitivity results from that same lap and fixed random state 42:

| Method / setting | Window | Flagged samples | Segments |
| --- | ---: | ---: | ---: |
| Statistical, threshold 4 | 15 | 66 | 35 |
| Statistical, threshold 6 | 15 | 24 | 18 |
| Statistical, threshold 8 | 15 | 6 | 5 |
| Statistical, threshold 4 | 31 | 39 | 28 |
| Statistical, threshold 6 | 31 | 12 | 10 |
| Statistical, threshold 8 | 31 | 7 | 7 |
| Statistical, threshold 4 | 62 | 48 | 25 |
| Statistical, threshold 6 | 62 | 9 | 9 |
| Statistical, threshold 8 | 62 | 8 | 8 |
| Isolation Forest, contamination 0.01 | 31 | 8 | 8 |
| Isolation Forest, contamination 0.03 | 31 | 24 | 23 |
| Isolation Forest, contamination 0.08 | 31 | 64 | 55 |

For every row, at least one segment center recurred within 100 m for another
setting of the same method. Segment counts and exact boundaries still varied
substantially with settings, particularly for Isolation Forest. The dashboard
does not treat these recurrences as verified concerns.

## Tests and commands

Automated tests mock FastF1/network methods for success, failure, partial data,
and comparison flows. They check distance alignment with different sampling
frequencies, duplicate and missing values, optional channels, the delta sign,
sensitivity settings, retrieval state, and Streamlit rendering. The cached
real-data integration above is a separate manual check using FastF1's local
cache.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -q app.py src pages tests
.venv/bin/python -m pip check
.venv/bin/python -m streamlit run app.py
```

Executed in the project environment on **2026-10-10**:

- `.venv/bin/python -m pytest -q` — **54 passed**.
- `.venv/bin/python -m ruff check .` — **All checks passed**.
- `.venv/bin/python -m compileall -q app.py src pages tests` — completed with
  no diagnostics.
- `.venv/bin/python -m pip check` — **No broken requirements found**. Pip
  warned that its user cache directory was not writable and disabled that
  cache; the dependency check itself completed successfully.
- `.venv/bin/python -m streamlit run app.py --server.headless true
  --server.port 8772 --browser.gatherUsageStats false` — server started, and
  `curl -sS -i http://localhost:8772/_stcore/health` returned HTTP **200**
  with `ok`.

The cached-session integration command and request were:

```bash
.venv/bin/python - <<'PY'
from src.data.fastf1_loader import load_session, load_driver_telemetry
session = load_session(2026, "Bahrain Grand Prix", "R", cache_dir=".fastf1-cache")
reference = load_driver_telemetry(session, "ALB", lap_number=31)
comparison = load_driver_telemetry(session, "ALB", lap_number=34)
PY
```

That session call was verified from FastF1 logs to use cached inputs. No
uncached network retrieval was performed or claimed in this Phase 8 check.
