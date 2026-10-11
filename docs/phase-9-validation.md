# Phase 9: Engineering credibility and telemetry validation

Validation performed on **2026-10-10 UTC** with FastF1 **3.8.3** and the
existing `.fastf1-cache`. This was actual public FastF1 telemetry read from the
local cache, not a new uncached network fetch. FastF1's logs explicitly said
`Using cached data` for session, car, position, and weather inputs during the
manual load. The application still labels per-request cache/network origin as
**unknown** because the project loader and FastF1 API do not expose reliable
per-request provenance; it does not generalize the observed log into app
metadata.

## Data path and lap comparability

The flow is `list_events` → `load_session` → driver selection → lap eligibility
checks → `load_driver_telemetry` → quality validation → distance alignment →
charts, calculated interpretation, and in-memory exports. Lap eligibility uses
available explicit fields: a lap must have a number and a recorded LapTime,
must not be marked inaccurate or deleted, and must not have pit-in or pit-out
markers. Excluded rows display their reasons. If validity markers are absent,
the application warns that it cannot filter on those fields; missing optional
markers do not automatically disqualify a timed lap. Differences in compound,
stint, track status, and nearest session-weather readings remain visible
context and are warnings rather than automatic exclusions.

The request was:

```python
session = load_session(2026, "Bahrain Grand Prix", "R")
```

FastF1 returned **22 drivers**, **1,145 lap rows**, and 31 lap-table columns.
For **ALB**, reference lap **31** and comparison lap **34** were both marked
`IsAccurate=True`, had recorded lap times, no deletion marker, and no pit-in or
pit-out markers. They shared stint 4, SOFT compound, and track-status code `1`.
`TyreLife` was missing for both. The nearest weather samples to lap midpoint
were 19.060 s and 10.918 s away respectively. These samples reported air
temperature 27.4/27.6 °C, track temperature 33.6/33.4 °C, humidity 82.1/81.5%,
no rainfall, and wind speed 2.1 m/s. Sample offsets are included to avoid
presenting a sparse nearest sample as an exact lap-wide average.

Lap 31 contained **790 rows**, lap 34 **763 rows**; both had 18 provider
columns with no missing values. Distance was increasing and had no duplicates
in either raw frame. Both had Date, Time, Distance, Speed, RPM, Throttle,
Brake, nGear, DRS, status, and spatial fields. Throttle ranged from 0 to 100;
Brake was boolean. Their common distance interval was approximately
0.455–5,486.224 m. The 5 m shared-distance grid contained 1,099 points.
Continuous signals use linear interpolation only between adjacent finite
samples; missing gaps are not bridged and no values are extrapolated.
Brake and gear use the nearest source sample. Native provider traces remain
separately plotted. Difference summaries include finite grid coverage.

Calculated maximum absolute differences for lap 34 minus lap 31 were:

- **Speed:** −33.367 km/h at 4,195.455 m (186.126 vs 152.758 km/h); mean absolute difference 6.368 km/h; coverage 1,099/1,099.
- **RPM:** +2,234.415 rpm at 1,930.455 m (8,684.819 vs 10,919.234 rpm); mean absolute difference 401.717 rpm; coverage 1,099/1,099.
- **Throttle:** −85.523 percentage points at 4,500.455 m (100.000 vs 14.477%); mean absolute difference 4.999 percentage points; coverage 1,099/1,099.

At the largest speed-difference location, both aligned brake samples were
active and the gears were 7 and 6; interpolated lap-local times were 74.268 s
and 74.709 s. Braking and gear timing are context, not a demonstrated cause.
The comparison is not controlled for driver inputs, traffic, tyres, weather,
track evolution, or other race conditions, and it does not establish a
power-unit issue.

## Anomaly feature and unit audit

The observed feature and local reference were traced to the same selected
feature column. A raw level uses the current FastF1 channel; a `*_change`
feature is the difference between the current row and the immediately
preceding cleaned row after distance sorting; missing values are not bridged.
The local reference is the median of preceding
feature values in the selected window. The earlier interface omitted the
feature definition and units, so a raw throttle value could look like a
transformed or standardized score.

A deterministic regression fixture sets raw throttle to **1.87%** against a
preceding median of **100.00%**. The updated explanation identifies the raw
Throttle level, uses `%` for both values, and reports a separate unitless
robust-scale deviation. This is a software test fixture, not an F1 sample.
For actual public **ALB lap 31**, the statistical method (threshold 6, window
31) used 790 rows and flagged **12 samples in 10 segments**. One flagged raw
Throttle level was 8.700% against a preceding median of 100.000%, with a 9.13
robust-scale deviation. These data are unlabelled screening results, not
fault labels or evaluation metrics. FastF1 throttle values outside 0–100% are
reported and retained, not clipped; none occurred on these two comparison
laps.

The anomaly page distinguishes the raw channel/value, selected feature
definition/unit, preceding-window feature reference, contextual robust
deviation, model score definition, selected rule, distance/time, brake/gear
context, and surrounding provider samples. Statistical score is a robust-scale
deviation; Isolation Forest's negative decision function is a separate
unitless in-sample score. Neither is a cause or fault probability.

## Dashboard and retrieval status

Streamlit AppTest exercised the overview, lap explorer, anomaly page, synthetic
pages, and Engineering Reports with deterministic fixtures. Interactions
covered lap selection and comparison, sensitivity analysis, report downloads,
empty state, partial telemetry, and simulated retrieval failure. The actual
cached Bahrain session was also run through AppTest: ALB lap 31 vs 34 produced
the values above with no page exception; the anomaly page consumed actual ALB
lap 31 with no exception and rendered its samples, charts, and download
controls. The case study is calculated from selected FastF1 frames and is not
hard-coded.

The overview now explains the main engineering question, links to the relevant
pages, displays an actionable empty state, and only shows a featured result
after a real comparison exists in the current app session. Engineering Reports
can download the selected real lap comparison as a source-labelled CSV and
Markdown report with lap identifiers, conditions, alignment method, coverage,
retrieval status, and calculated deltas. Real telemetry reports remain
separate from synthetic evaluation reports, and downloads are built in memory.

The session-load completion timestamp records when the loader returned. It is
not a request-start time and does not prove a network fetch. Explicit reload
invokes the loader again, but FastF1 may use its cache. The app does not claim
fresh-network or cache-hit provenance. FastF1 also emitted upstream tyre-stint
correction and recorded race-completion timing warnings during the cached
session load; the application does not suppress or rewrite them.

## Remaining limits

FastF1 public telemetry is not the complete internal power-unit sensor suite.
The lap comparison is descriptive and does not control for all race context.
Throttle and brake are the provider's reported pedal channels, not internal
engine sensor values. Real FastF1 data has no verified anomaly labels, so no
real-data precision, recall, F1, false-positive rate, fault diagnosis, or
failure prediction is claimed. Synthetic benchmark labels and metrics remain
in the separate synthetic workflow.

The desktop browser automation runtime could not start in this environment, so
I could not capture a browser screenshot. Streamlit AppTest rendering and a
headless server health check were used instead.

## Verification performed

On 2026-10-11, from the repository root, I ran:

```text
.venv/bin/python -m pytest -q
65 passed in 6.07s

.venv/bin/python -m ruff check .
All checks passed!

.venv/bin/python -m compileall -q app.py src pages tests
completed successfully (no diagnostics)

.venv/bin/python -m pip check
No broken requirements found.

git diff --check
completed successfully (no whitespace errors)

curl -fsS http://localhost:8765/_stcore/health
ok
```

The pip check emitted a warning that the user's pip cache directory was not
writable; pip disabled that cache and still completed the dependency check.
Streamlit AppTest was also run against the cached Bahrain session for the
Explorer and anomaly page, as described above. A screenshot/browser automation
check could not be completed because the desktop browser automation runtime
failed to start; the app was checked through AppTest and the Streamlit health
endpoint instead.
