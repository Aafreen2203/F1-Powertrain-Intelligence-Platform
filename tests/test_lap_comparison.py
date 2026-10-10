import numpy as np
import pandas as pd
import pytest

from src.analytics.lap_comparison import (
    LapComparisonError,
    align_laps_by_distance,
    lap_difference_summary,
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
