import pandas as pd

from src.reporting.lap_comparison import LAP_COMPARISON_SOURCE, lap_comparison_exports


def test_lap_comparison_export_preserves_dashboard_values_and_source_metadata():
    summary = pd.DataFrame([{
        "comparison_lap": 34,
        "channel": "Speed",
        "distance_m": 4195.45,
        "reference_value": 186.12,
        "comparison_value": 152.76,
        "delta_comparison_minus_reference": -33.36,
        "mean_absolute_difference": 6.37,
        "valid_aligned_samples": 1099,
        "aligned_grid_samples": 1099,
        "coverage_fraction": 1.0,
        "reference_time_s": 74.27,
        "comparison_time_s": 74.71,
    }])
    metadata = {
        "year": 2026,
        "event": "Bahrain Grand Prix",
        "session": "R",
        "driver": "ALB",
        "reference_lap": 31,
        "comparison_laps": [34],
        "alignment_method": "shared distance grid",
        "retrieval": {"load_completed_at_utc": "2026-10-10T23:35:59Z", "cache_origin": "unknown"},
        "lap_context": [{"comparison_role": "reference", "Compound": "SOFT"}],
        "telemetry_quality": {"31": {"record_count": 790, "warnings": []}},
    }

    export, report = lap_comparison_exports(summary, metadata=metadata)

    assert export["data_source"].iat[0] == LAP_COMPARISON_SOURCE
    assert export["delta_comparison_minus_reference"].iat[0] == summary["delta_comparison_minus_reference"].iat[0]
    assert export["reference_lap"].iat[0] == 31
    assert export["cache_network_origin"].iat[0] == "unknown"
    assert '"record_count": 790' in export["telemetry_quality_json"].iat[0]
    assert "-33.360" in report
    assert "comparison lap minus reference lap" in report
    assert "cache/network origin: unknown" in report.lower()
    assert "PUBLIC FASTF1 TELEMETRY" in report
