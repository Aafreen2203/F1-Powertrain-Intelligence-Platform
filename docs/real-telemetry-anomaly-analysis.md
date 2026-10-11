# Real FastF1 telemetry anomaly review

## Data flow

Load a year, event, and session through **F1 Telemetry Explorer**. The existing
`src.data.fastf1_loader` module enables the project cache and loads the session.
**Telemetry Anomaly Analysis** reuses that in-memory session and calls the
existing `load_driver_telemetry` helper for the selected driver and lap. It
does not call FastF1 independently, load a whole championship, or replace
missing public channels with simulated readings. Driver and lap selection is
available on the analysis page after the year/event/session are loaded in the
explorer.

The analytics module uses whichever of `Speed`, `RPM`, `Throttle`, `Brake`,
and `nGear` are present and nonconstant. `Distance` is required. Distance is
parsed numerically, invalid distances are excluded, samples are stable-sorted
by distance, and duplicate distances keep the last provider sample. Provider
timestamps and values remain attached to that sample. Missing or infinite
channel values are not filled. Nonfinite values are counted and treated as
missing in the analysis copy. A channel is left out if it is unavailable,
constant, or has fewer than two finite readings; the quality summary
distinguishes these cases. Samples without any usable channel are counted
when removed. Isolation Forest scores only rows with complete values for its
available feature set; excluded rows remain visible and unscored.

## Features and methods

The statistical method computes absolute robust deviations for available
Speed, RPM, and Throttle levels and one-sample changes in those three signals.
Brake and nGear are contextual signals, not direct anomaly features. For each
sample it compares those values with a rolling median and median absolute
deviation from preceding samples only. The current and later samples do not
fit that sample's local reference. When MAD is zero or tiny, the scale falls
back to the preceding-window standard deviation, then a 1% underlying
channel-level floor (also for change features), with signal-specific minimum
scales for Speed, RPM, Throttle, and gear to avoid unbounded scores on
quantized or near-zero signals; wholly constant channels are
excluded. RPM level and change features are masked on gear-change samples and
the immediately following sample to reduce routine shift-transient flags.
Gear itself is available in charts and context but is not scored. If Brake is
available, its state is context only (not a scored anomaly feature), and
Speed/Throttle levels and changes are not scored on a braking sample or the
immediately following sample. The threshold is adjustable in the UI. This
causal rule still does not model corners, traffic, tyre state, driving style,
or session strategy.

Isolation Forest operates on available Speed, RPM, and Throttle levels and the
same derived change features; Brake and nGear are excluded as direct features.
It is seeded for reproducibility and uses a configurable
contamination setting. For one selected lap it is fit and scored on that same
unlabelled lap. Its scores are therefore exploratory and in-sample; there is
no test set, no verified anomaly label, and no precision, recall, F1, accuracy,
or false-positive rate. Neither method calls a flagged sample a confirmed
fault. The statistical explanation identifies the feature that crossed its
threshold. For Isolation Forest it identifies the largest contextual
deviation for review, not a causal feature attribution. Scores/rules mark
potentially unusual telemetry that merits engineering review with driving and
session context.

The flagged-sample table distinguishes raw channels from the selected feature.
A level feature such as `Throttle` is the current FastF1 channel sample; a
derived feature such as `Throttle_change` is current throttle minus the
immediately preceding cleaned row after distance sorting, in percentage points
per provider sample. Missing values are not bridged. Its local reference is
the preceding-window median in the same feature unit. The statistical score is a unitless robust-scale deviation;
Isolation Forest's negative decision-function score is unitless and separate
from the contextual feature deviation. FastF1 documents Speed in km/h, RPM in
rpm, Throttle on a 0–100% scale (with 104 sometimes indicating unavailable or
erroneous data), Brake as boolean applied/not-applied, and nGear as a gear
number. Out-of-range throttle values are reported but retained, not clipped.

Contiguous flagged samples form a segment; any clean or unscored sample breaks
the segment. The anomaly page charts actual provider samples against their
distance, marks potential anomalies on Speed and RPM traces, and can highlight
a chosen segment with surrounding distance context. It analyzes one lap at a
time. The F1 Telemetry Explorer separately compares selected laps using
distance alignment and documented interpolation; no page aligns by sample row
number. See [Phase 8 validation](phase-8-validation.md) for the method and
observed example.

## Quality and exports

The page reports input ordering problems, removed invalid distances and
duplicate distances, nonfinite channel counts, distance ordering after
cleanup, unavailable lap-validity markers, and unscored samples. Short laps,
empty laps, missing distance, and laps without usable varying channels produce
actionable messages. Network and session retrieval messages remain on the
explorer page.

CSV and Markdown downloads are generated only when requested. They are
downloaded through Streamlit and are not written into repository directories.
Exports carry the label `PUBLIC FASTF1 TELEMETRY · UNLABELLED`, selection
identifiers, method parameters, channel findings, and interpretation limits.
The Engineering Reports page retains its separate synthetic reports and
exposes the current real telemetry exports when analysis results are present
in the same app session.

FastF1 public telemetry is not internal power-unit instrumentation. Available
signals and sampling cadence vary by session and lap. Braking, shifting,
cornering, driver inputs, track conditions, or upstream data issues can cause
unusual values. Do not interpret these flags as engine failure diagnosis or
reliability prediction.

## Cached-session integration check

On **2026-10-10**, the new analysis module was run through the existing loader
against the cached **2026 Bahrain Grand Prix Race**, ALB lap **31** previously
loaded during Phase 7. FastF1 3.8.3 reported that the session inputs were read
from cache; this check did not need an uncached live request. The selected lap
had 790 rows and 18 provider columns; all 790 rows were usable after cleanup.
Speed, RPM, Throttle, Brake, and nGear were present; there were no invalid or
duplicate distances and no nonfinite values in these channels. With the
statistical method at threshold 6 and window 31, 12 samples in 10 contiguous
segments were flagged as potential anomalies; 61 samples were unscored because
causal warm-up and masked braking/gear-shift context left them without a score.
The maximum score was 47.641. These are counts and scores for one unlabelled lap, not measured
anomaly-detection performance. FastF1 continued to report upstream tyre-stint
and race-completion warnings documented in [Phase 7 validation](phase-7-validation.md).

The final check commands on 2026-10-10 were:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app.py src pages tests
.venv/bin/python -m pip check
```

Results: **43 tests passed**, Ruff passed, `compileall` completed without
diagnostics, and `pip check` found no broken requirements. The headless app
was started with:

```bash
.venv/bin/python -m streamlit run app.py --server.headless true --server.port 8769 --browser.gatherUsageStats false
```

Its `/_stcore/health` endpoint returned **200 `ok`**. The FastF1 integration
run used cached data; dashboard tests use mocked loader responses and require
no network.
