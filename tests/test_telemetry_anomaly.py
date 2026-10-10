import numpy as np
import pandas as pd
import pytest

from src.analytics.telemetry_anomaly import (
    TelemetryAnalysisError,
    analyze_telemetry,
    summarize_anomaly_segments,
)
from src.reporting.telemetry import PUBLIC_SOURCE, telemetry_export_frames


def make_telemetry(n=80):
    distance = np.arange(n, dtype=float) * 10
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=n, freq="100ms", tz="UTC"),
        "Time": pd.to_timedelta(np.arange(n) / 10, unit="s"),
        "Distance": distance,
        "Speed": 180 + 4 * np.sin(distance / 80),
        "RPM": 9000 + 100 * np.sin(distance / 60),
        "Throttle": np.full(n, 80.0),
        "Brake": np.zeros(n, dtype=bool),
        "nGear": np.full(n, 5),
    })


def test_causal_baseline_scores_actual_samples_and_does_not_mutate_input():
    telemetry = make_telemetry()
    telemetry.loc[45, "Speed"] = 300
    before = telemetry.copy(deep=True)
    result = analyze_telemetry(telemetry, threshold=4, window=15)
    assert result.samples["Distance"].is_monotonic_increasing
    assert result.samples.loc[45, "is_potential_anomaly"]
    assert result.samples.loc[45, "feature_or_channel"].startswith("Speed")
    assert "Speed" in result.samples.columns
    assert not any("synthetic" in column.lower() for column in result.samples.columns)
    pd.testing.assert_frame_equal(telemetry, before)
    assert "preceding" in result.quality["method_note"]


def test_causal_scores_do_not_change_when_only_future_values_change():
    original = make_telemetry()
    changed_future = original.copy()
    changed_future.loc[60:, "Speed"] = 500
    first = analyze_telemetry(original, window=15).samples
    second = analyze_telemetry(changed_future, window=15).samples
    np.testing.assert_allclose(first.loc[:55, "anomaly_score"], second.loc[:55, "anomaly_score"], equal_nan=True)


def test_missing_optional_channels_nan_infinite_and_duplicate_distance_are_reported():
    telemetry = make_telemetry().drop(columns=["Throttle", "Brake", "nGear"])
    telemetry.loc[30, "Speed"] = np.inf
    telemetry.loc[31, "RPM"] = np.nan
    duplicate = telemetry.iloc[[20]].copy()
    duplicate["Date"] = duplicate["Date"] + pd.to_timedelta(1, unit="ms")
    telemetry.loc[20, "Speed"] = 1
    telemetry = pd.concat([telemetry, duplicate], ignore_index=True)
    telemetry.loc[80, "Distance"] = 200
    result = analyze_telemetry(telemetry)
    assert result.available_channels == ["Speed", "RPM"]
    assert result.quality["duplicate_distance_samples_removed"] == 1
    assert result.quality["nonfinite_channel_values"]["Speed"] == 1
    assert result.quality["distance_duplicate_count_after_cleanup"] == 0
    assert result.quality["distance_monotonic_after_cleanup"]
    assert result.quality["source_ordering_violations"] > 0
    duplicate_distance_row = result.samples.loc[result.samples["Distance"] == 200].iloc[0]
    assert duplicate_distance_row["Date"] == pd.Timestamp("2026-01-01T00:00:02.001Z")


def test_constant_only_and_short_laps_report_insufficient_data():
    constant = make_telemetry()
    constant["Speed"] = 100
    constant["RPM"] = 9000
    constant["Throttle"] = 50
    with pytest.raises(TelemetryAnalysisError, match="constant"):
        analyze_telemetry(constant)
    short = make_telemetry(19)
    with pytest.raises(TelemetryAnalysisError, match="at least 20"):
        analyze_telemetry(short)


def test_missing_distance_and_invalid_parameters_are_explicit():
    with pytest.raises(TelemetryAnalysisError, match="No telemetry"):
        analyze_telemetry(pd.DataFrame())
    with pytest.raises(TelemetryAnalysisError, match="Distance"):
        analyze_telemetry(make_telemetry().drop(columns="Distance"))
    with pytest.raises(ValueError, match="threshold"):
        analyze_telemetry(make_telemetry(), threshold=0)


def test_isolation_forest_scores_deterministically_and_discloses_in_sample_fit():
    telemetry = make_telemetry()
    telemetry.loc[50, "Speed"] = 320
    first = analyze_telemetry(telemetry, method="Isolation Forest", random_state=9)
    second = analyze_telemetry(telemetry, method="Isolation Forest", random_state=9)
    pd.testing.assert_series_equal(first.samples["is_potential_anomaly"], second.samples["is_potential_anomaly"])
    pd.testing.assert_series_equal(first.samples["anomaly_score"], second.samples["anomaly_score"])
    assert "same unlabelled lap" in first.quality["method_note"]


def test_gear_shift_context_masks_rpm_change_feature():
    telemetry = make_telemetry()
    telemetry["Speed"] = 180
    telemetry["Throttle"] = 80
    telemetry.loc[40, "nGear"] = 6
    telemetry.loc[40, "RPM"] = 8600
    result = analyze_telemetry(telemetry, threshold=100, window=15)
    assert pd.isna(result.samples.loc[40, "anomaly_score"])
    assert not result.samples.loc[40, "is_potential_anomaly"]


def test_brake_context_does_not_score_a_braking_speed_transient_as_anomaly():
    telemetry = make_telemetry()
    telemetry["RPM"] = 9000
    telemetry["Throttle"] = 80
    telemetry["nGear"] = 5
    telemetry.loc[50, "Speed"] = 45
    telemetry.loc[50, "Brake"] = True
    result = analyze_telemetry(telemetry, threshold=4, window=15)
    assert not result.samples.loc[50, "is_potential_anomaly"]
    assert "Brake" in result.quality["context_channels"]


def test_segment_summary_keeps_clean_sample_gaps_separate():
    samples = pd.DataFrame({
        "Distance": [0, 1, 2, 3, 4],
        "is_potential_anomaly": [False, True, True, False, True],
        "segment_id": pd.Series([pd.NA, 1, 1, pd.NA, 2], dtype="Int64"),
        "feature_or_channel": ["", "Speed", "Speed", "", "RPM"],
        "anomaly_score": [0, 7, 8, 0, 9],
        "explanation": ["none", "high", "high", "none", "rpm"],
    })
    segments = summarize_anomaly_segments(samples)
    assert segments["sample_count"].tolist() == [2, 1]
    assert segments["distance_start_m"].tolist() == [1.0, 4.0]


def test_exports_include_public_source_session_and_limitation_labels():
    result = analyze_telemetry(make_telemetry())
    sample_export, quality_export, report = telemetry_export_frames(
        result,
        metadata={"year": 2026, "event": "Example GP", "session": "R", "driver": "1", "lap": 2},
        parameters={"method": "Statistical baseline", "threshold": 6, "contamination": 0.03, "window": 31},
    )
    assert set(sample_export["data_source"]) == {PUBLIC_SOURCE}
    assert sample_export["event"].iat[0] == "Example GP"
    assert "potential anomaly" in report.lower()
    assert "precision" in report.lower()
    assert set(quality_export["data_source"]) == {PUBLIC_SOURCE}
