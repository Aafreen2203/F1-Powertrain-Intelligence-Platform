"""Overview page for the F1 Powertrain Intelligence dashboard."""
import streamlit as st

st.set_page_config(page_title="F1 Powertrain Intelligence", page_icon="🏎️", layout="wide")
st.title("F1 Powertrain Intelligence Platform")
st.caption("Independent portfolio analysis using public Formula 1 data and illustrative synthetic sensors.")
st.warning("Not affiliated with Red Bull Racing. No confidential team or power-unit data is used.")
st.subheader("Engineering question")
st.markdown("**Where does a driver's speed profile differ most between comparable laps, and which available telemetry channels help explain the difference?** The comparison uses same-session laps, explicit FastF1 validity/pit markers, and distance alignment. It describes observed driving telemetry; it does not diagnose internal power-unit health.")
st.page_link("pages/1_F1_Telemetry_Explorer.py", label="Start with public F1 session analysis", icon="🏎️", use_container_width=True)

loaded_key = st.session_state.get("f1_loaded_key")
retrieval = st.session_state.get("f1_retrieval_status", {})
if loaded_key:
    st.success(f"Current public session: {loaded_key[0]} {loaded_key[1]} · {loaded_key[2]} · load status: {retrieval.get('state', 'unknown')}.")
    selected = retrieval.get("selected_lap", {})
    if selected:
        st.caption(f"Selected telemetry: {selected.get('driver', 'unknown')} lap {selected.get('lap', 'unknown')} · {selected.get('sample_count', 'unknown')} provider samples · channels: {', '.join(selected.get('available_channels', []))}.")
else:
    st.info("No real session is loaded in this app session. Open F1 Telemetry Explorer, load the event list, then request one completed session. Network retrieval is on demand; failures are shown and never replaced with synthetic values.")

case_study = st.session_state.get("f1_lap_comparison")
st.subheader("Featured calculated lap comparison")
if case_study is None:
    st.info("No comparison result is available yet. Load a session and select a reference lap plus one eligible comparison lap to build this case study from actual FastF1 samples.")
else:
    metadata = case_study["metadata"]
    st.markdown(f"**{metadata['year']} {metadata['event']} · {metadata['session']} · {metadata['driver']} · reference lap {metadata['reference_lap']} · comparison laps {', '.join(map(str, metadata['comparison_laps']))}**")
    speed_rows = case_study["summary"].loc[case_study["summary"]["channel"] == "Speed"]
    if speed_rows.empty:
        st.warning("This selection has no jointly available Speed samples; the app cannot state a speed-profile difference.")
    else:
        largest = speed_rows.loc[speed_rows["delta_comparison_minus_reference"].abs().idxmax()]
        st.metric("Largest absolute aligned speed difference", f"{largest['delta_comparison_minus_reference']:+.2f} km/h", f"lap {int(largest['comparison_lap'])} minus reference at {largest['distance_m']:.1f} m")
        st.caption(f"Calculated over {largest['valid_aligned_samples']} of {largest['aligned_grid_samples']} shared-grid points ({largest['coverage_fraction']:.1%} finite coverage). This is an interpolated observation; lap context and limitations are shown in the Explorer.")

st.subheader("Explore")
columns = st.columns(3)
for column, path, label in (
    (columns[0], "pages/1_F1_Telemetry_Explorer.py", "F1 Telemetry Explorer"),
    (columns[1], "pages/2_Telemetry_Anomaly_Analysis.py", "Public telemetry anomaly review"),
    (columns[2], "pages/3_Data_Quality.py", "Data quality"),
):
    column.page_link(path, label=label, use_container_width=True)
columns = st.columns(3)
for column, path, label in (
    (columns[0], "pages/4_Model_Evaluation.py", "Synthetic model evaluation"),
    (columns[1], "pages/5_Engineering_Reports.py", "Engineering reports"),
    (columns[2], "pages/2A_Synthetic_Sensor_Lab.py", "Synthetic Sensor Lab"),
):
    column.page_link(path, label=label, use_container_width=True)

with st.expander("Data sources and interpretation limits"):
    st.markdown("**Real FastF1 telemetry** supplies public car signals such as speed, RPM, throttle, brake state, gear, timing, and session context where available. It does not expose the full internal power-unit sensor suite. Lap differences can reflect driver inputs, tyres, weather, traffic, track status, setup, and session evolution; no causal fault or reliability conclusion follows.\n\n**Synthetic Sensor Lab** is a separate controlled workflow for simulated temperature, pressure, vibration, and rotational-speed signals with injected labels. Those samples and evaluation metrics are not F1 measurements or real engine-failure prediction.")
st.caption(f"Session load completed: {retrieval.get('load_completed_at_utc', 'not available')} UTC · cache/network origin: {retrieval.get('cache_origin', 'unknown')}. The completion timestamp does not identify the origin.")
