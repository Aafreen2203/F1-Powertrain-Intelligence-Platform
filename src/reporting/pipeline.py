"""Standalone reproducible synthetic sensor analysis and report pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px

from src.data.synthetic_sensors import generate_sensor_data
from src.models.anomaly import EvaluationResult, evaluate_anomaly_methods
from src.validation.quality import validate_frame

FEATURES = ["temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm"]
DATASET_TYPE = "SYNTHETIC — illustrative simulated sensor readings"


@dataclass
class PipelineResult:
    """In-memory results plus paths for files written by the pipeline."""

    data: pd.DataFrame
    quality: dict
    sensor_summary: pd.DataFrame
    evaluation: EvaluationResult
    artifacts: dict[str, Path]


def run_synthetic_pipeline(
    *,
    output_dir: str | Path = "reports",
    frame: pd.DataFrame | None = None,
    seed: int = 42,
    generated_at: datetime | None = None,
) -> PipelineResult:
    """Generate/load synthetic data, validate, analyse, evaluate, and export.

    This callable is independent of Streamlit. It writes timestamped CSV,
    Markdown, and interactive HTML outputs to `output_dir` and returns every
    computed result and artifact path. The time column must be chronological.
    """
    data = generate_sensor_data(seed=seed) if frame is None else frame.copy()
    required = ["timestamp", *FEATURES, "anomaly_label", "event_label"]
    quality = validate_frame(
        data,
        required_columns=required,
        expected_types={"timestamp": "datetime", **{feature: "numeric" for feature in FEATURES},
                        "anomaly_label": "integer"},
        timestamp_col="timestamp",
        expected_interval="1s",
    )
    if not quality["passed"]:
        raise ValueError(f"Synthetic dataset failed validation: {quality['failures']}")
    summary = data[FEATURES].agg(["count", "mean", "std", "min", "max"]).T
    evaluation = evaluate_anomaly_methods(data, feature_cols=FEATURES)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_time = generated_at or datetime.now(UTC)
    if report_time.tzinfo is None:
        report_time = report_time.replace(tzinfo=UTC)
    stamp = report_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    quality_rows = [
        {"dataset_type": DATASET_TYPE, "check": "record_count", "value": quality["record_count"]},
        {"dataset_type": DATASET_TYPE, "check": "column_count", "value": quality["column_count"]},
        {"dataset_type": DATASET_TYPE, "check": "missing_cells", "value": sum(quality["missing_counts"].values())},
        {"dataset_type": DATASET_TYPE, "check": "duplicate_records", "value": quality["duplicate_records"]},
        {"dataset_type": DATASET_TYPE, "check": "passed", "value": quality["passed"]},
        {"dataset_type": DATASET_TYPE, "check": "warnings", "value": "; ".join(quality["warnings"])},
    ]
    quality_table = pd.DataFrame(quality_rows)
    metrics = evaluation.metrics.assign(dataset_type=DATASET_TYPE)
    summary.index.name = "signal"
    summary_export = summary.reset_index().assign(dataset_type=DATASET_TYPE)
    summary_export.to_csv(output_path / f"sensor_summary_{stamp}.csv", index=False)
    quality_table.to_csv(output_path / f"data_quality_{stamp}.csv", index=False)
    metrics.to_csv(output_path / f"model_metrics_{stamp}.csv", index=False)

    long_data = data.melt(id_vars=["timestamp", "anomaly_label", "event_label"],
                          value_vars=FEATURES, var_name="signal", value_name="reading")
    chart = px.line(
        long_data,
        x="timestamp",
        y="reading",
        facet_row="signal",
        color="event_label",
        title="SYNTHETIC — illustrative sensor trends with generated event labels",
        labels={"event_label": "Generated scenario", "reading": "Simulated reading"},
    )
    chart.write_html(output_path / f"sensor_trends_{stamp}.html", include_plotlyjs="cdn")

    headers = list(metrics.columns)
    metric_markdown = "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n"
    for _, row in metrics.iterrows():
        metric_markdown += "| " + " | ".join(str(row[column]) for column in headers) + " |\n"
    report = f"""# Synthetic Sensor Analysis Report

Generated: {report_time.astimezone(UTC).isoformat()}

> {DATASET_TYPE}. These readings and event scenarios are not actual F1 power-unit measurements or genuine engine failures.

## Data quality
- Records: {quality['record_count']}
- Missing cells: {sum(quality['missing_counts'].values())}
- Duplicate records: {quality['duplicate_records']}
- Validation passed: {quality['passed']}
- Warnings: {('; '.join(quality['warnings']) or 'None')}

## Detection evaluation
Chronological split index: {evaluation.split_index}. Training used {evaluation.train_normal_count} known-normal rows from the earlier block. Labels are not model features; earlier labels select normal training rows, and later labels evaluate the holdout.

{metric_markdown}

Precision, recall, F1, and false-positive rate refer to generated scenario labels only. This semi-supervised synthetic evaluation does not establish real-world fault diagnosis, reliability, or failure prediction.
"""
    report_path = output_path / f"engineering_report_{stamp}.md"
    report_path.write_text(report, encoding="utf-8")
    artifacts = {
        "sensor_summary": output_path / f"sensor_summary_{stamp}.csv",
        "data_quality": output_path / f"data_quality_{stamp}.csv",
        "model_metrics": output_path / f"model_metrics_{stamp}.csv",
        "sensor_chart": output_path / f"sensor_trends_{stamp}.html",
        "markdown_report": report_path,
    }
    return PipelineResult(data, quality, summary, evaluation, artifacts)
