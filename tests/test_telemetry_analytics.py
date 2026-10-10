import pandas as pd
import pytest

from src.analytics.telemetry import lap_kpis, telemetry_profile


def test_telemetry_profile_uses_only_available_signals():
    result = telemetry_profile(pd.DataFrame({"Speed": [100, 110], "Gear": [2, 3], "Driver": ["A", "A"]}))
    assert result["record_count"] == 2
    assert set(result["signal_summary"].index) == {"Speed", "Gear"}
    assert result["correlations"].shape == (2, 2)


def test_telemetry_profile_excludes_time_duration_columns_from_signal_stats():
    telemetry = pd.DataFrame({
        "Speed": [100, 110],
        "Time": pd.to_timedelta([0, 1], unit="s"),
        "Date": pd.date_range("2026-01-01", periods=2),
    })
    result = telemetry_profile(telemetry)
    assert list(result["signal_summary"].index) == ["Speed"]


def test_lap_kpis_count_incomplete_laps_and_compute_descriptive_stats():
    laps = pd.DataFrame({"Driver": ["A", "A", "B"], "LapTime": pd.to_timedelta([90, 92, None], unit="s")})
    result = lap_kpis(laps).set_index("Driver")
    assert result.loc["A", "completed_timed_laps"] == 2
    assert result.loc["A", "best_lap_seconds"] == 90
    assert result.loc["A", "median_lap_seconds"] == 91
    assert result.loc["B", "incomplete_laps"] == 1
    assert pd.isna(result.loc["B", "best_lap_seconds"])


def test_lap_kpis_reject_missing_required_column():
    with pytest.raises(ValueError, match="LapTime"):
        lap_kpis(pd.DataFrame({"Driver": ["A"]}))
