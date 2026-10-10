"""Overview page for the F1 Powertrain Intelligence dashboard."""
import streamlit as st

st.set_page_config(page_title="F1 Powertrain Intelligence", page_icon="🏎️", layout="wide")
st.title("F1 Powertrain Intelligence Platform")
st.caption("Independent portfolio analysis using public Formula 1 data and illustrative synthetic sensors.")
st.warning("Not affiliated with Red Bull Racing. No confidential team or power-unit data is used.")
st.markdown("Use public FastF1 session telemetry as the primary exploratory data source. The separately labelled Synthetic Sensor Lab is for controlled demonstrations only; its simulated readings are not F1 measurements, actual engine failures, diagnoses, or predictions.")
st.subheader("Start with a real session")
st.markdown("1. Open **F1 Telemetry Explorer** and load an event list, then select a year, Grand Prix, and session.\n2. Open **Telemetry Anomaly Analysis**, select a driver and lap, and inspect unusual samples in context.\n3. Export the selected lap's results and quality summary from **Engineering Reports**.")
st.info("FastF1 retrieval requires network access and is subject to session availability. If the network or requested data is unavailable, the real telemetry workflow reports that state and does not substitute synthetic data.")
