# FastF1 retrieval diagnostics and validation

## What the reported production output establishes

The supplied Streamlit Cloud logs identify
`fastf1._api.SessionNotAvailableError: No data for this session!` for the 2024
Bahrain Grand Prix Practice 1 request. FastF1 also failed to retrieve session
information, session and track status, lap timing, and weather; car and position
telemetry were unavailable. `Session.load()` nevertheless logged 20 drivers.
This establishes a partial load in the reported Cloud run. The provided logs
do not include the HTTP response status or underlying transport exception for
the failed resources, so they do not establish why Cloud received no data.

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
the session appear complete. Cache initialization occurs outside the timing
retrieval error boundary, so a cache setup error retains its own actionable
message rather than being mislabeled as a missing timing response.

## Python and dependency compatibility evidence

The local environment used for this check was Python 3.14.7 with FastF1 3.8.3.
FastF1's installed package metadata declares `Requires-Python >=3.10`. The same
interpreter successfully retrieved the public session described below. This
shows that FastF1 3.8.3 can operate in this local Python 3.14.7 environment;
it does not prove that the separate Streamlit Cloud instance has equivalent
network access, cache permissions, or runtime state. No dependency was changed
or pinned because this investigation did not demonstrate a version-compatibility
failure.

The supplied Cloud runtime is Python 3.14.8 with FastF1 3.8.3, so those two
reported versions differ locally only by the Python patch release. The
repository's `.github/workflows/ci.yml` tests Python 3.11. Runtime dependencies
in `requirements.txt` are unpinned; therefore, Streamlit, pandas, NumPy, SciPy,
scikit-learn, and Plotly versions in Cloud cannot be inferred from this
checkout, and no lock file establishes that they match local versions. Local
versions on 2026-10-11 were Streamlit 1.65.0, pandas 2.3.3, NumPy 2.5.4,
SciPy 1.18.1, scikit-learn 1.9.1, Plotly 7.1.0, and FastF1 3.8.3. Since
FastF1 successfully retrieved both the reported session and a second session
under local Python 3.14.7, the available evidence does not support changing
Python or dependency versions as the fix.

`requirements.txt` is the authoritative runtime dependency file selected by
Streamlit Community Cloud. `pyproject.toml` contains Ruff and pytest settings,
not a second runtime dependency declaration.

## Local live-data validation

Retrieved on **2026-10-11 UTC** using FastF1 3.8.3, a fresh temporary disk
cache per request, and the shared `src.data.fastf1_loader.load_session()` path:

- **2024 Bahrain Grand Prix — Practice 1**, requested as
  `load_session(2024, "Bahrain Grand Prix", "FP1")`. The schedule resolves
  this to `Practice 1` for `FORMULA 1 GULF AIR BAHRAIN GRAND PRIX 2024`,
  scheduled 2024-02-29 11:30 UTC with `F1ApiSupport=True`. The request
  succeeded: **449 lap rows**, **355 timed lap records**, **20 drivers**, 20
  car-data and 20 position-data driver streams, and **82 weather rows**.
  Session info, driver info, session status, track status, timing, car, position,
  and weather stages all completed in the local run.
- **2024 Bahrain Grand Prix — Practice 2** also resolved to its official
  session and succeeded: **511 lap rows**, **430 timed lap records**, 20
  drivers, 20 car-data and 20 position-data driver streams, and 82 weather
  rows.
- **2025 Bahrain Grand Prix — Practice 1** succeeded as another comparison:
  **426 lap rows**, **281 timed lap records**, 20 drivers, 20 car-data and 20
  position-data driver streams, and 80 weather rows.

The exact 2024 Bahrain FP1 session reported by Cloud therefore loaded in a
fresh local cache, and the 2024 schedule/event/session mapping is valid. The
production failure is not reproducible here. The evidence does not distinguish
a transient upstream response from a Cloud network, cache, or other runtime
condition; no specific cause should be claimed without further Cloud-side
request evidence.

- The 2025 session exposed **426 lap rows**, **31 columns**, **20 driver
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

The app passes the selected schedule `EventName` and `FP1` code to
`fastf1.get_session(int(season), event, session_name)`. The 2024 schedule
resolves this to the intended official Bahrain GP Practice 1 session. Session
retrieval is not wrapped in Streamlit's `cache_data` or `cache_resource`;
FastF1's disk cache is enabled under a writable temporary-directory path
unless `F1_CACHE_DIR` is set. The inspected code provides no evidence for a
stale Streamlit cache or incorrect session selection.

FastF1 3.8.3's installed `_api.fetch_page()` requests its primary livetiming
source and retries its mirror when the primary HTTP status is at least 400. If
the final status is not HTTP 200, it returns `None` without retaining that
status; a caller can then raise `SessionNotAvailableError`. Transport
exceptions can be logged with their traceback by FastF1's soft-load wrapper.
The supplied Cloud excerpt includes `SessionNotAvailableError` but no HTTP
status or transport exception, so it does not identify whether a remote
response, HTTP error, timeout, or Cloud network restriction caused the failure.

The retrievals were run from the repository root using the repository `.venv` Python:

```bash
.venv/bin/python - <<'PY'
from src.data.fastf1_loader import load_session, get_session_laps

for year, event, code in (
    (2024, "Bahrain Grand Prix", "FP1"),
    (2024, "Bahrain Grand Prix", "FP2"),
    (2025, "Bahrain Grand Prix", "FP1"),
):
    session = load_session(year, event, code)
    laps = get_session_laps(session, load_if_needed=False)
    print(year, event, code, session.name, len(laps),
          int(laps["LapTime"].notna().sum()), len(session.drivers))
PY
```

## Verifying the Streamlit Cloud failure

This workspace cannot inspect the deployed app's runtime or its complete Cloud
logs. After this change is deployed through the repository's normal GitHub /
Streamlit integration:

1. Open **Manage app → Logs** in Streamlit Community Cloud.
2. Open **FastF1 Retrieval Diagnostics** and press **Run both session checks**.
   It uses the shared loader and cache configuration for Bahrain FP1 and FP2,
   and reports Python/FastF1 versions, resolved session names, whether FastF1
   logged load completion, timing validation, lap counts, and safe exception
   details from FastF1/server logs.
3. In the Explorer, select **2024**, **Bahrain Grand Prix**, and **FP1** and
   press **Load / reload selected session** to verify the normal flow.
4. If FastF1's soft loader catches a failure, search the server log for
   `FastF1 partial-load failure for`. The following traceback identifies
   the FastF1 loading stage and underlying exception. Cache initialization
   failures and exceptions propagated by FastF1 are logged by the shared
   loader as well. The page displays a concise retry/select-another-session
   message and does not substitute synthetic data. For the car/position
   warnings, search for `FastF1 reports` and check the session-specific entry;
   FastF1 3.8.3 does not retain the associated response status in this path.
5. If the load succeeds, verify that driver and lap selectors are populated.
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
.venv/bin/python -m pytest -q                 # 88 passed
.venv/bin/python -m ruff check .               # All checks passed
.venv/bin/python -m compileall -q app.py src pages tests
.venv/bin/python -m pip check                  # No broken requirements found
git diff --check                               # Passed
```

The `pip check` command printed a warning that the user's pip cache directory
was not writable, disabled that cache, and then reported no broken requirements.
