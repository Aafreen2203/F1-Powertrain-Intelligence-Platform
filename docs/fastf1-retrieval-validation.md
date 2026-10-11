# FastF1 retrieval diagnostics and validation

## What the reported production output establishes

The supplied Streamlit Cloud summary says that several FastF1 resources failed,
that car and position telemetry were unavailable, and that `Session.load()`
still logged 20 drivers. It does not include the exceptions, HTTP status codes,
URLs, or full FastF1 traceback. It therefore establishes an incomplete load,
but does not identify whether the Cloud failure was caused by networking,
upstream responses, cache permissions, or another error. The year was also not
included in the summary.

FastF1 3.8.3 source explains the misleading completion line: its `Session.load()`
calls independently wrapped loaders for session info, results, session and
track status, lap timing, car/position telemetry, and weather. The wrappers
catch many exceptions and log a short warning plus a traceback at DEBUG. The
method then logs the number of drivers from its results table. That count is
not a validation of timing or telemetry availability.

There is a distinct FastF1 path for car and position feeds: `Session.load()`
catches `SessionNotAvailableError` and emits only a generic “data is
unavailable” warning. In this version, `fetch_page()` tries a mirror when the
primary response status is at least 400, then returns `None` if the final
response is not HTTP 200. It does not preserve the response status in the
warning. The new server log associates those warnings with the selected session
and records that FastF1 omitted the status; it cannot recover a status code
that FastF1 has already discarded. Full Cloud HTTP status evidence therefore
still requires logs from below this FastF1 request layer or an upstream fix.

There is a distinct FastF1 path for car and position feeds: `Session.load()`
catches `SessionNotAvailableError` and emits only a generic “data is
unavailable” warning. In this version, `fetch_page()` tries a mirror when the
primary response status is at least 400, then returns `None` if the final
response is not HTTP 200. It does not preserve the response status in the
warning. The new server log associates those warnings with the selected session
and records that FastF1 omitted the status; it cannot recover a status code
that FastF1 has already discarded. Full Cloud HTTP status evidence therefore
still requires logs from below this FastF1 request layer or an upstream fix.

The installed 3.8.3 `Session.load` signature accepts keyword-only `laps`,
`telemetry`, `weather`, `messages`, and `livedata` arguments. The shared loader
uses the supported keyword names and explicitly requests laps; it does not
depend on positional argument ordering.

The shared loader now temporarily captures FastF1's soft-failure traceback
records and forwards the stage and exception traceback to server logs. It does
not change FastF1's logging level or put the traceback in the page. After
`Session.load()`, it checks that lap timing is accessible and non-empty, has
`Driver`, `LapNumber`, and `LapTime` columns, and contains at least one timed
driver lap. If not, it raises a retrieval error and the affected pages offer a
retry or another session. A session with timed laps but missing optional weather
can still be used; weather context is omitted. If selected-lap telemetry cannot
be extracted, the existing telemetry error path remains explicit and no
synthetic replacement is used. Successful validation also logs lap-row/driver
counts and the availability counts for optional car, position, and weather
data; a missing optional collection is marked unavailable instead of making
the session appear complete.

## Python and dependency compatibility evidence

The local environment used for this check was Python 3.14.7 with FastF1 3.8.3.
FastF1's installed package metadata declares `Requires-Python >=3.10`. The same
interpreter successfully retrieved the public session described below. This
shows that FastF1 3.8.3 can operate in this local Python 3.14.7 environment;
it does not prove that the separate Streamlit Cloud instance has equivalent
network access, cache permissions, or runtime state. No dependency was changed
or pinned because this investigation did not demonstrate a version-compatibility
failure.

`requirements.txt` is the authoritative runtime dependency file selected by
Streamlit Community Cloud. `pyproject.toml` contains Ruff and pytest settings,
not a second runtime dependency declaration.

## Local live-data validation

Retrieved on **2026-10-11 UTC** using FastF1 3.8.3, its disk cache, and the
shared `src.data.fastf1_loader.load_session()` path:

- **2025 Bahrain Grand Prix — Practice 1**, scheduled 2025-04-11 11:30 UTC.
  FastF1's 2025 schedule marks this event as supporting its F1 API.
- Schedule lookup, session information, driver information, session status,
  track status, extended timing, timing app data, car data, position data, and
  weather requests all returned successfully in this local run and were written
  to the FastF1 cache.
- The session exposed **426 lap rows**, **31 columns**, **20 driver
  abbreviations**, **20 car-data driver streams**, **20 position-data driver
  streams**, and **80 weather rows**. Lap data had 1,887 missing cells, mostly
  optional or incomplete timing fields; 145 of the 426 `LapTime` values were
  missing. This is why lap-level eligibility checks remain necessary.
- For a concrete telemetry extraction, the fastest accurate timed lap found
  for Lando Norris (`NOR`) was lap **12**, **1:33.204**. FastF1 returned **698
  rows** and 18 columns. None of the returned telemetry columns had missing
  cells; timestamps and circuit distance were monotonically increasing, with
  no duplicate full rows. Available primary channels ranged over Distance
  −0.02–5,368.19 m, Speed 68–315 km/h, RPM 5,523–12,208, Throttle 0–100%, and
  gear 2–8. Brake was present as a Boolean channel (567 false and 131 true
  samples).
- FastF1 did emit per-driver “Car data is incomplete!” and “Position data is
  incomplete!” warnings during that run. The requested streams still loaded;
  these warnings describe incomplete individual driver traces, not a failed
  whole-session request. No claim is made that the local run reproduces the
  Cloud failure.

The successfully loaded session was also passed through local Streamlit
`AppTest` runs for both telemetry pages: the explorer rendered 20 driver
options and six charts; the anomaly page rendered five charts, three download
buttons, and a real-telemetry analysis result. Neither page raised an app
exception. Streamlit emitted its usual missing-`ScriptRunContext` warnings
because `AppTest` runs in bare mode; those are harness warnings, not page
errors. This verifies local page consumption of the retrieved data, not the
deployed Cloud runtime.

The validation was performed with the following command shape from the
repository root (the actual run used the repository's `.venv` Python and the
default temporary cache):

```bash
.venv/bin/python - <<'PY'
from src.data.fastf1_loader import load_session, get_session_laps, load_driver_telemetry

session = load_session(2025, "Bahrain Grand Prix", "FP1")
laps = get_session_laps(session, load_if_needed=False)
valid = laps[(laps["Driver"] == "NOR") & laps["LapTime"].notna()]
valid = valid[valid["IsAccurate"].fillna(False)]
lap_number = int(valid.sort_values("LapTime").iloc[0]["LapNumber"])
telemetry = load_driver_telemetry(session, "NOR", lap_number=lap_number)
print(laps.shape, telemetry.shape, list(telemetry.columns))
PY
```

## Verifying the Streamlit Cloud failure

This workspace cannot inspect the deployed app's runtime or its complete Cloud
logs. After this change is deployed through the repository's normal GitHub /
Streamlit integration:

1. Open **Manage app → Logs** in Streamlit Community Cloud.
2. In the app, select the exact year shown in the production failure (the
   supplied summary omitted it), **Bahrain Grand Prix**, and **Practice 1**;
   press **Load / reload selected session**.
3. If FastF1's soft loader catches a failure, search the server log for
   `FastF1 partial-load failure for`. The following traceback identifies
   the FastF1 loading stage and underlying exception. Cache initialization
   failures and exceptions propagated by FastF1 are logged by the shared
   loader as well. The page displays a concise retry/select-another-session
   message and does not substitute synthetic data. For the car/position
   warnings, search for `FastF1 reports` and check the session-specific entry;
   FastF1 3.8.3 does not retain the associated response status in this path.
4. If the load succeeds, verify that driver and lap selectors are populated.
   Then open **Telemetry Anomaly Analysis**, select a driver and timed lap, and
   confirm the public telemetry page reports its available channels. Optional
   weather may be absent without preventing lap selection; car/position traces
   may remain incomplete for individual drivers.

If the Cloud traceback points to a timeout, DNS/TLS error, HTTP status, or
cache write failure, that exact log evidence can distinguish the next fix. The
summary supplied for this change did not include that detail, so no Cloud-side
root cause is asserted here. Synthetic sensor outputs remain a separately
labelled demonstration and are not evidence about real engine reliability.

## Checks run

From the repository root, the automated local checks completed with:

```bash
.venv/bin/python -m pytest -q                 # 86 passed
.venv/bin/python -m ruff check .               # All checks passed
.venv/bin/python -m compileall -q app.py src pages tests
.venv/bin/python -m pip check                  # No broken requirements found
git diff --check                               # Passed
```

The `pip check` command printed a warning that the user's pip cache directory
was not writable, disabled that cache, and then reported no broken requirements.
