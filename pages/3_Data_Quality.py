"""Data quality summary for synthetic sensors and loaded public telemetry."""
import pandas as pd
import streamlit as st

from src.dashboard_data import cached_synthetic_data
from src.validation.quality import validate_frame

st.title("Data Quality")
st.subheader("Synthetic sensor dataset")
st.caption("Illustrative generated data, separate from public telemetry.")
data = cached_synthetic_data()
sensor_result = validate_frame(data, required_columns=["timestamp", "temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm", "anomaly_label", "event_label"], numeric_ranges={"temperature_c": (40, 140), "pressure_kpa": (100, 400), "vibration_mm_s": (0, 20), "rotational_speed_rpm": (0, 20000)}, timestamp_col="timestamp", expected_interval="1s")
c1, c2, c3 = st.columns(3)
c1.metric("Records", sensor_result["record_count"])
c2.metric("Missing values", sum(sensor_result["missing_counts"].values()))
c3.metric("Validation status", "Passed" if sensor_result["passed"] else "Review")
sensor_rows = [
    {"Check": "Duplicate records", "Result": sensor_result["duplicate_records"]},
    {"Check": "Non-monotonic timestamps", "Result": sensor_result.get("non_monotonic_timestamps", "unavailable")},
    *[{"Check": f"Missing · {column}", "Result": count}
      for column, count in sensor_result["missing_counts"].items() if count],
    *[{"Check": "Warning", "Result": warning} for warning in sensor_result["warnings"]],
]
st.dataframe(pd.DataFrame(sensor_rows or [{"Check": "Missing values", "Result": "None"}]).astype({"Result": str}), hide_index=True, width="stretch")
st.subheader("Loaded public telemetry")
telemetry = st.session_state.get("f1_telemetry")
if telemetry is None:
    st.info("No public telemetry is loaded in this app session. Visit F1 Telemetry Explorer and load a session/lap.")
else:
    st.caption("Provider data is shown as retrieved; no imputation or fabricated values are used.")
    telemetry_result = validate_frame(telemetry, timestamp_col="Date" if "Date" in telemetry else None)
    c1, c2, c3 = st.columns(3)
    c1.metric("Provider records", telemetry_result["record_count"])
    c2.metric("Missing cells", sum(telemetry_result["missing_counts"].values()))
    c3.metric("Validation status", "Passed" if telemetry_result["passed"] else "Review")
    telemetry_rows = [
        {"Check": "Duplicate records", "Result": telemetry_result["duplicate_records"]},
        *[{"Check": f"Missing · {column}", "Result": count}
          for column, count in telemetry_result["missing_counts"].items() if count],
        *[{"Check": "Warning", "Result": warning} for warning in telemetry_result["warnings"]],
    ]
    st.dataframe(pd.DataFrame(telemetry_rows or [{"Check": "Missing values", "Result": "None"}]).astype({"Result": str}), hide_index=True, width="stretch")
    diagnostic_payloads = {"public_telemetry_quality": telemetry_result}
with st.expander("Technical Diagnostics", expanded=False):
    st.json({"synthetic_sensor_quality": sensor_result, **(diagnostic_payloads if telemetry is not None else {})})
