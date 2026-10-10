import pandas as pd
from fastf1.core import Telemetry

import src.dashboard_data as dashboard_data


def _frame() -> pd.DataFrame:
    count = 80
    distance = pd.Series(range(count), dtype="float64") * 10
    return pd.DataFrame({
        "Distance": distance,
        "Speed": 180 + 4 * (distance / 80).map(lambda value: value % 1),
        "RPM": 9000 + distance,
        "Time": pd.to_timedelta(range(count), unit="ms") * 100,
    })


def test_fastf1_telemetry_passes_through_cached_analysis_without_mutation():
    source = Telemetry(_frame())
    before = pd.DataFrame(source).copy(deep=True)
    result = dashboard_data.cached_telemetry_anomaly(source)

    assert len(result.samples) == 80
    pd.testing.assert_frame_equal(pd.DataFrame(source), before)


def test_cache_key_tracks_telemetry_content_and_analysis_parameters(monkeypatch):
    calls = []

    def fake_analyze(telemetry, **parameters):
        calls.append((telemetry.copy(deep=True), parameters))
        return len(calls)

    monkeypatch.setattr(dashboard_data, "analyze_telemetry", fake_analyze)
    dashboard_data._cached_telemetry_anomaly.clear()
    initial = Telemetry(_frame())
    dashboard_data.cached_telemetry_anomaly(initial)
    dashboard_data.cached_telemetry_anomaly(Telemetry(_frame()))
    assert len(calls) == 1  # Identical telemetry and controls reuse the cache.

    changed = _frame()
    changed.loc[45, "Speed"] += 1
    dashboard_data.cached_telemetry_anomaly(Telemetry(changed))
    assert len(calls) == 2  # Changed values produce a distinct cache entry.

    dashboard_data.cached_telemetry_anomaly(Telemetry(_frame()), window=33)
    assert len(calls) == 3  # Every analysis control remains part of the key.


def test_fingerprint_tracks_index_columns_and_dtypes():
    frame = _frame()
    baseline = dashboard_data._telemetry_fingerprint(frame)
    assert dashboard_data._telemetry_fingerprint(frame.copy()) == baseline
    assert dashboard_data._telemetry_fingerprint(frame.set_axis(range(1, 81))) != baseline
    assert dashboard_data._telemetry_fingerprint(frame.rename(columns={"Speed": "Velocity"})) != baseline
    assert dashboard_data._telemetry_fingerprint(frame.astype({"Speed": "float32"})) != baseline
