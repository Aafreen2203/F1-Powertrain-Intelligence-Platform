import numpy as np
import pandas as pd
import pytest

from src.analytics.lap_comparison import (
    LapComparisonError,
    align_laps_by_distance,
    classify_laps,
    lap_difference_summary,
    lap_weather_at_midpoint,
    unavailable_lap_markers,
)


def _lap(distance, speed, *, brake=None, gear=None):
    frame = pd.DataFrame({
        "Distance": distance,
        "Time": pd.to_timedelta(np.asarray(distance) / 50, unit="s"),
        "Speed": speed,
        "RPM": np.asarray(speed) * 50,
    })
    if brake is not None:
        frame["Brake"] = brake
    if gear is not None:
        frame["nGear"] = gear
    return frame


def test_alignment_uses_distance_not_row_number_and_delta_sign_is_comparison_minus_reference():
    reference = _lap([0, 10, 20, 30], [100, 100, 100, 100])
    comparison = _lap([0, 7, 14, 21, 28, 30], [110] * 6)
    aligned = align_laps_by_distance(reference, comparison, step_m=5)
    assert aligned["Distance"].is_monotonic_increasing
    assert aligned["Distance"].iloc[0] == 0
    assert aligned["Distance"].iloc[-1] == 30
    assert (aligned["delta_Speed"] == 10).all()
    summary = lap_difference_summary(aligned)
    assert summary.loc[summary["channel"] == "Speed", "delta_comparison_minus_reference"].iat[0] == 10
    assert "reference_time_s" in aligned and "comparison_time_s" in aligned


def test_missing_optional_channels_are_not_fabricated_and_brake_gear_use_nearest_sample():
    reference = _lap([0, 10, 20], [100, 110, 120], brake=[False, True, False], gear=[3, 4, 4])
    comparison = _lap([0, 20], [101, 121])
    reference = reference.drop(columns="RPM")
    comparison = comparison.drop(columns="RPM")
    aligned = align_laps_by_distance(reference, comparison, step_m=5)
    assert "delta_Speed" in aligned
    assert "delta_RPM" not in aligned
    assert aligned["reference_Brake"].tolist() == [False, False, True, True, False]
    assert aligned["reference_nGear"].tolist() == [3, 3, 4, 4, 4]
    assert "comparison_Brake" not in aligned


def test_duplicate_distances_keep_last_and_missing_values_remain_missing():
    reference = _lap([0, 10, 10, 20], [90, 100, 105, np.nan])
    comparison = _lap([0, 10, 20], [95, 105, 115])
    aligned = align_laps_by_distance(reference, comparison, step_m=10)
    assert aligned.loc[aligned["Distance"] == 10, "reference_Speed"].iat[0] == 105
    # Missing source observations are not bridged or extrapolated.
    assert pd.isna(aligned.loc[aligned["Distance"] == 20, "reference_Speed"]).all()


def test_disjoint_distance_ranges_and_invalid_step_are_reported():
    with pytest.raises(LapComparisonError, match="no overlapping"):
        align_laps_by_distance(_lap([0, 1], [1, 2]), _lap([3, 4], [2, 3]))
    with pytest.raises(ValueError, match="step_m"):
        align_laps_by_distance(_lap([0, 1], [1, 2]), _lap([0, 1], [2, 3]), step_m=0)


def test_lap_eligibility_explains_timing_validity_deletion_and_pit_exclusions():
    laps = pd.DataFrame({
        "LapNumber": [1, 2, 3, 4, 5, 6],
        "LapTime": pd.to_timedelta([90, 91, 92, 93, 94, None], unit="s"),
        "IsAccurate": [True, False, True, True, True, True],
        "Deleted": [False, False, True, False, False, False],
        "DeletedReason": [None, None, "track limits", None, None, None],
        "PitInTime": [pd.NaT, pd.NaT, pd.NaT, pd.to_timedelta(80, unit="s"), pd.NaT, pd.NaT],
        "PitOutTime": [pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.to_timedelta(1, unit="s"), pd.NaT],
    })
    before = laps.copy(deep=True)
    result = classify_laps(laps)
    assert result["comparison_eligible"].tolist() == [True, False, False, False, False, False]
    assert "inaccurate" in result.loc[1, "exclusion_reasons"]
    assert "deleted: track limits" in result.loc[2, "exclusion_reasons"]
    assert "pit-in" in result.loc[3, "exclusion_reasons"]
    assert "pit-out" in result.loc[4, "exclusion_reasons"]
    assert "timed lap unavailable" in result.loc[5, "exclusion_reasons"]
    pd.testing.assert_frame_equal(laps, before)


def test_lap_eligibility_does_not_reject_when_optional_markers_are_absent():
    laps = pd.DataFrame({
        "LapNumber": [1], "LapTime": pd.to_timedelta([90], unit="s"),
    })
    result = classify_laps(laps)
    assert bool(result["comparison_eligible"].iat[0])
    assert result["exclusion_reasons"].iat[0] == ""
    assert unavailable_lap_markers(laps) == ["IsAccurate", "Deleted", "PitInTime", "PitOutTime"]


def test_weather_context_uses_nearest_sample_to_lap_midpoint():
    weather = pd.DataFrame({
        "Time": pd.to_timedelta([10, 50, 90], unit="s"),
        "TrackTemp": [40.0, 41.0, 42.0],
    })
    lap = pd.Series({
        "LapStartTime": pd.to_timedelta(30, unit="s"),
        "LapTime": pd.to_timedelta(40, unit="s"),
    })
    selected = lap_weather_at_midpoint(weather, lap)
    assert selected["TrackTemp"] == 41.0
    assert selected["lap_midpoint_offset_seconds"] == 0
    assert lap_weather_at_midpoint(pd.DataFrame(), lap) is None


def test_difference_summary_reports_finite_alignment_coverage():
    reference = _lap([0, 10, 20, 30], [100, 110, np.nan, 130])
    comparison = _lap([0, 5, 10, 15, 20, 25, 30], [110, 110, 110, 130, 130, 130, 130])
    aligned = align_laps_by_distance(reference, comparison, step_m=5)
    summary = lap_difference_summary(aligned)
    speed = summary.loc[summary["channel"] == "Speed"].iloc[0]
    assert speed["aligned_grid_samples"] == len(aligned)
    assert speed["valid_aligned_samples"] < speed["aligned_grid_samples"]
    assert 0 < speed["coverage_fraction"] < 1
