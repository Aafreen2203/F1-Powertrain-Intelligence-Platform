"""Download computed synthetic benchmark and data quality reports."""
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src.dashboard_data import cached_synthetic_data
from src.models.anomaly import evaluate_anomaly_methods
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
