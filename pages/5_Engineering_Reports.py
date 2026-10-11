"""Download computed synthetic benchmark and data quality reports."""
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src.dashboard_data import cached_synthetic_data
from src.models.anomaly import evaluate_anomaly_methods
from src.reporting.lap_comparison import lap_comparison_exports
from src.reporting.telemetry import telemetry_export_frames
from src.validation.quality import validate_frame

st.title("Engineering Reports")
st.caption("Computed synthetic demonstration data; no F1 performance results are inferred.")
data = cached_synthetic_data()
quality = validate_frame(data, timestamp_col="timestamp", expected_interval="1s")
evaluation = evaluate_anomaly_methods(data, feature_cols=["temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm"])
metrics = evaluation.metrics.assign(dataset_type="SYNTHETIC · illustrative sensor benchmark")
now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
st.subheader("Model metrics")
st.dataframe(metrics, width="stretch", hide_index=True)
st.download_button("Download model metrics CSV", data=metrics.to_csv(index=False), file_name=f"synthetic_model_metrics_{now}.csv", mime="text/csv")
st.subheader("Quality summary")
quality_rows = [{"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "record_count", "value": str(quality["record_count"])}, {"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "column_count", "value": str(quality["column_count"])}, {"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "missing_values", "value": str(sum(quality["missing_counts"].values()))}, {"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "duplicate_records", "value": str(quality["duplicate_records"])}, {"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "passed", "value": str(quality["passed"])}, {"dataset_type": "SYNTHETIC · illustrative sensor benchmark", "check": "warnings", "value": "; ".join(quality["warnings"])}]
quality_table = pd.DataFrame(quality_rows)
st.dataframe(quality_table, width="stretch", hide_index=True)
st.download_button("Download quality summary CSV", data=quality_table.to_csv(index=False), file_name=f"synthetic_quality_summary_{now}.csv", mime="text/csv")
metric_headers = list(metrics.columns)
metric_md = "| " + " | ".join(metric_headers) + " |\n| " + " | ".join(["---"] * len(metric_headers)) + " |\n"
for _, metric_row in metrics.iterrows():
    metric_md += "| " + " | ".join(str(metric_row[col]) for col in metric_headers) + " |\n"
report = f"""# Synthetic Sensor Analysis Report

Generated: {datetime.now(UTC).isoformat()}

> SYNTHETIC DATA: readings and injected event labels are illustrative, not actual Formula 1 power-unit measurements or genuine engine failures.

## Data quality
- Records: {quality['record_count']}
- Columns: {quality['column_count']}
- Missing cells: {sum(quality['missing_counts'].values())}
- Duplicate records: {quality['duplicate_records']}
- Validation passed: {quality['passed']}
- Warnings: {('; '.join(quality['warnings']) or 'None')}

## Detection evaluation
Chronological split index: {evaluation.split_index}. Earlier training records used: {evaluation.train_normal_count} known-normal rows. Ground-truth labels were excluded from feature inputs and used to select normal training rows and evaluate the later holdout.

{metric_md}

Precision is the share of flags matching injected labels; recall is the share of injected records detected; F1 is their harmonic mean; false-positive rate is the share of normal holdout records flagged. This labelled synthetic benchmark does not establish real-world fault diagnosis or failure prediction.
"""
st.download_button("Download Markdown report", data=report, file_name=f"synthetic_engineering_report_{now}.md", mime="text/markdown")

st.divider()
st.subheader("Real FastF1 telemetry review")
real_review = st.session_state.get("real_telemetry_anomaly")
if real_review is None:
    st.info("No real telemetry analysis is available in this app session. Load a session in F1 Telemetry Explorer, then analyse a lap in Telemetry Anomaly Analysis.")
else:
    real_result = real_review["result"]
    real_metadata = real_review["metadata"]
    real_parameters = real_review["parameters"]
    sample_frame, real_quality, real_report = telemetry_export_frames(
        real_result, metadata=real_metadata, parameters=real_parameters,
        retrieval=real_review.get("retrieval"),
    )
    st.caption("PUBLIC FASTF1 TELEMETRY · UNLABELLED · exports contain potential anomalies, not confirmed faults.")
    st.write(f"{real_metadata['year']} {real_metadata['event']} · {real_metadata['session']} · "
             f"{real_metadata['driver']} lap {real_metadata['lap']} · "
             f"{real_result.quality['potential_anomaly_sample_count']} flagged samples")
    real_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    st.download_button("Download public telemetry anomaly CSV", sample_frame.to_csv(index=False),
                       file_name=f"fastf1_telemetry_anomalies_{real_stamp}.csv", mime="text/csv")
    st.download_button("Download public telemetry quality CSV", real_quality.to_csv(index=False),
                       file_name=f"fastf1_telemetry_quality_{real_stamp}.csv", mime="text/csv")
    st.download_button("Download public telemetry report", real_report,
                       file_name=f"fastf1_telemetry_report_{real_stamp}.md", mime="text/markdown")

comparison = st.session_state.get("f1_lap_comparison")
if comparison is None:
    st.info("No calculated public FastF1 lap comparison is available in this app session. Select eligible laps in F1 Telemetry Explorer first.")
else:
    comparison_frame, comparison_report = lap_comparison_exports(
        comparison["summary"], metadata=comparison["metadata"]
    )
    st.divider()
    st.subheader("Public FastF1 lap-comparison case study")
    st.caption("Calculated distance-aligned values · comparison minus reference · observational, not a power-unit diagnosis.")
    st.dataframe(comparison_frame, width="stretch", hide_index=True)
    st.download_button("Download public lap comparison CSV", comparison_frame.to_csv(index=False),
                       file_name="fastf1_lap_comparison.csv", mime="text/csv")
    st.download_button("Download public lap comparison report", comparison_report,
                       file_name="fastf1_lap_comparison_report.md", mime="text/markdown")
