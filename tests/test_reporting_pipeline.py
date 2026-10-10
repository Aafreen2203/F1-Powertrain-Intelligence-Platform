from datetime import UTC, datetime

import pandas as pd
import pytest

from src.reporting.pipeline import DATASET_TYPE, run_synthetic_pipeline


def test_standalone_pipeline_writes_timestamped_labelled_artifacts(tmp_path):
    result = run_synthetic_pipeline(output_dir=tmp_path, seed=15,
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert len(result.data) == 700
    assert result.quality["passed"]
    assert len(result.sensor_summary) == 4
    assert set(result.artifacts) == {"sensor_summary", "data_quality", "model_metrics", "sensor_chart", "markdown_report"}
    assert all(path.exists() for path in result.artifacts.values())
    assert all("20260102T030405Z" in path.name for path in result.artifacts.values())
    metrics = pd.read_csv(result.artifacts["model_metrics"])
    assert set(metrics["dataset_type"]) == {DATASET_TYPE}
    summary = pd.read_csv(result.artifacts["sensor_summary"])
    assert set(summary["dataset_type"]) == {DATASET_TYPE}
    report = result.artifacts["markdown_report"].read_text(encoding="utf-8")
    assert "SYNTHETIC" in report
    assert "not actual F1 power-unit measurements" in report


def test_pipeline_rejects_data_that_fails_quality_validation(tmp_path):
    frame = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=3, freq="s")})
    with pytest.raises(ValueError, match="failed validation"):
        run_synthetic_pipeline(output_dir=tmp_path, frame=frame)
