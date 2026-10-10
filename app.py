"""Overview page for the F1 Powertrain Intelligence dashboard."""
import streamlit as st

from src.data.synthetic_sensors import generate_sensor_data
from src.validation.quality import validate_frame

st.set_page_config(page_title="F1 Powertrain Intelligence", page_icon="🏎️", layout="wide")
st.title("F1 Powertrain Intelligence Platform")
st.caption("Independent portfolio analysis using public Formula 1 data and illustrative synthetic sensors.")
st.warning("Not affiliated with Red Bull Racing. No confidential team or power-unit data is used.")
st.markdown("This project explores public F1 telemetry and a separate synthetic sensor benchmark. Synthetic readings are illustrative and must not be interpreted as measurements, actual engine failures, diagnosis, or predictions.")
sensor = generate_sensor_data(n_samples=700, seed=42)
quality = validate_frame(sensor, required_columns=["timestamp", "temperature_c", "pressure_kpa"], timestamp_col="timestamp", expected_interval="1s")
c1, c2, c3 = st.columns(3)
c1.metric("Synthetic sensor records", f"{len(sensor):,}")
c2.metric("Injected illustrative events", f"{int(sensor['anomaly_label'].sum()):,}")
c3.metric("Quality check", "Passed" if quality["passed"] else "Review")
st.caption("KPIs above are computed from a fixed-seed synthetic demonstration, not live F1 measurements.")
st.markdown("**Data sources**\n\n- Public telemetry: retrieved on demand from FastF1 when available.\n- Synthetic sensors: seeded simulated temperature, pressure, vibration, and rotational speed.")
st.info("Select a page from the sidebar. Public session retrieval needs network access and may be unavailable for some events or channels.")
