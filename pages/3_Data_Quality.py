"""Data quality summary for synthetic sensors and loaded public telemetry."""
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
st.json(sensor_result)
st.subheader("Loaded public telemetry")
telemetry = st.session_state.get("f1_telemetry")
if telemetry is None:
    st.info("No public telemetry is loaded in this app session. Visit F1 Telemetry Explorer and load a session/lap.")
else:
    st.caption("Provider data is shown as retrieved; no imputation or fabricated values are used.")
    st.json(validate_frame(telemetry, timestamp_col="Date" if "Date" in telemetry else None))
