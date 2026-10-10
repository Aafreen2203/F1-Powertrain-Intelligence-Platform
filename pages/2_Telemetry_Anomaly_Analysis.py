"""Exploratory anomaly screening for the currently loaded public FastF1 lap."""
import plotly.graph_objects as go
import streamlit as st

from src.analytics.telemetry_anomaly import (
    TelemetryAnalysisError,
    sensitivity_analysis,
    summarize_anomaly_segments,
)
from src.dashboard_data import cached_telemetry_anomaly
from src.data.fastf1_loader import FastF1DataError, list_drivers, load_driver_telemetry
from src.reporting.telemetry import telemetry_export_frames

st.title("Telemetry Anomaly Analysis")
st.warning(
    "REAL PUBLIC TELEMETRY · Flags indicate unusual samples for engineering review. "
    "They are not confirmed mechanical faults or failure predictions."
)
st.caption("FastF1 data is unlabelled. No precision, recall, F1, accuracy, or false-positive rate is reported.")

session = st.session_state.get("f1_loaded_session")
session_key = st.session_state.get("f1_loaded_key")
st.session_state.pop("real_telemetry_anomaly", None)
if session is None or session_key is None:
    st.info("Load a public year, event, and session in **F1 Telemetry Explorer** first. Synthetic data is never substituted.")
    st.stop()

season, event_name, session_name = session_key
st.markdown(f"**Loaded session:** {season} {event_name} · {session_name}")
drivers = list_drivers(session)
if not drivers:
    st.warning("FastF1 returned no driver lap records for this session.")
    st.stop()

driver = st.selectbox("Driver", drivers, key="anomaly_driver")
laps = session.laps[session.laps["Driver"].astype(str) == driver]
eligible = laps.dropna(subset=["LapTime"]) if "LapTime" in laps else laps.iloc[0:0]
if "IsAccurate" in eligible:
    eligible = eligible[eligible["IsAccurate"].fillna(False)]
for pit_col in ("PitInTime", "PitOutTime"):
    if pit_col in eligible:
        eligible = eligible[eligible[pit_col].isna()]
if eligible.empty and "LapTime" in laps:
    eligible = laps.dropna(subset=["LapTime"])
    st.warning("No accurate non-pit laps are marked by FastF1; options use timed laps only.")
lap_options = sorted(eligible["LapNumber"].dropna().astype(int).unique()) if "LapNumber" in eligible else []
if not lap_options:
    st.warning("No timed lap is available for this driver.")
    st.stop()
lap_number = st.selectbox("Lap", lap_options, key="anomaly_lap")

with st.expander("Detection controls", expanded=True):
    method = st.selectbox("Analysis method", ["Statistical baseline", "Isolation Forest"])
    threshold = st.slider("Causal robust-deviation threshold", 2.0, 12.0, 6.0, 0.5,
                          disabled=method != "Statistical baseline")
    contamination = st.slider("Isolation Forest contamination", 0.01, 0.15, 0.03, 0.01,
                               disabled=method != "Isolation Forest")
    window = st.slider("Preceding context window (samples)", 5, 101, 31, 2)

try:
    telemetry = load_driver_telemetry(session, driver, lap_number=int(lap_number))
    result = cached_telemetry_anomaly(
        telemetry, method=method, threshold=threshold, contamination=contamination,
        window=window, random_state=42,
    )
except (FastF1DataError, TelemetryAnalysisError, ValueError) as exc:
    st.warning(f"This lap cannot be analysed: {exc}")
    st.stop()

metadata = {
    "year": season, "event": event_name, "session": session_name,
    "driver": driver, "lap": int(lap_number),
}
method_parameters = {
    "method": method,
    "threshold": threshold if method == "Statistical baseline" else None,
    "contamination": contamination if method == "Isolation Forest" else None,
    "window": window,
}
st.session_state["real_telemetry_anomaly"] = {
    "result": result, "metadata": metadata,
    "parameters": method_parameters,
}

c1, c2, c3 = st.columns(3)
c1.metric("Usable samples", result.quality["rows_used"])
c2.metric("Potential anomaly samples", result.quality["potential_anomaly_sample_count"])
c3.metric("Contiguous segments", result.quality["potential_anomaly_segment_count"])
st.caption(f"Available channels: {', '.join(result.available_channels)} · Brake and nGear, when present, supply context and are not scored directly.")
st.caption(str(result.quality["method_note"]))
st.info("A sample outlier is a mathematical result, not an engineering concern by itself. Driver inputs, braking, shifts, cornering, tyres, weather, traffic, session type, and data issues may explain unusual public telemetry. FastF1 has no verified anomaly ground truth here; no accuracy, precision, recall, F1, false-positive rate, or failure prediction is available.")
st.json({key: value for key, value in result.quality.items()
         if key in {"source_ordering_violations", "duplicate_distance_samples_removed",
                    "invalid_distance_samples_removed", "nonfinite_channel_values",
                    "channel_availability", "samples_without_usable_channels_removed",
                    "distance_monotonic_after_cleanup", "distance_duplicate_count_after_cleanup",
                    "unscored_samples", "warnings"}})

segments = summarize_anomaly_segments(result.samples)
with st.expander("Sensitivity analysis · not accuracy validation", expanded=False):
    st.caption("The selected unlabelled lap is rescored at fixed statistical thresholds (4/6/8) and three windows (approximately half, selected, and double the selected window), plus Isolation Forest contamination settings (0.01/0.03/0.08) at the selected window. Random state is fixed at 42. The recurrence column is true when at least one segment center reappears within 100 m under another setting of the same method; it is a descriptive stability check, not ground truth.")
    st.caption("The extra fits run only after you press the button, so the initial page load does not repeat the selected-lap analysis.")
    if st.button("Run sensitivity analysis", key="run_telemetry_sensitivity"):
        try:
            sensitivity = sensitivity_analysis(telemetry, window=window, random_state=42)
            st.dataframe(sensitivity, width="stretch", hide_index=True)
        except (TelemetryAnalysisError, ValueError) as exc:
            st.warning(f"Sensitivity analysis unavailable for this lap: {exc}")
    else:
        st.caption("Run the calculation when needed; the default page load stays focused on the selected analysis.")
if segments.empty:
    st.success("No samples met the selected anomaly rule on this lap.")
else:
    st.subheader("Potential anomaly segments")
    st.dataframe(segments, width="stretch", hide_index=True)
    selected_segment = st.selectbox("Inspect segment in surrounding telemetry", segments["segment_id"].tolist())
    selected = segments.loc[segments["segment_id"] == selected_segment].iloc[0]
    context = st.slider("Context either side (metres)", 25, 1000, 250, 25)
    distance_low = max(float(result.samples["Distance"].min()), selected["distance_start_m"] - context)
    distance_high = min(float(result.samples["Distance"].max()), selected["distance_end_m"] + context)
    rule = (
        f"threshold {selected['configured_threshold']:.2f}"
        if method == "Statistical baseline"
        else f"Isolation Forest contamination {selected['configured_contamination']:.2f}"
    )
    st.caption(f"Segment {selected_segment}: {selected['top_feature']} reached score {selected['max_score']:.2f} ({rule}). "
               f"Observed feature values range from {selected['observed_min']:.2f} to {selected['observed_max']:.2f}, "
               f"with local preceding-window median {selected['local_reference_median']:.2f}; "
               f"context: {selected['brake_context']}, gear samples {selected['gear_context']}. "
               "Review the original trace and race context; this is not a fault diagnosis.")

st.subheader("Selected lap telemetry")
chart_channels = [channel for channel in ("Speed", "RPM", "Throttle", "Brake", "nGear")
                  if channel in result.samples]
for channel in chart_channels:
    values = result.samples[channel]
    if not values.notna().any():
        continue
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result.samples["Distance"], y=values, mode="lines",
                             name=channel, connectgaps=False))
    flagged = result.samples[result.samples["is_potential_anomaly"]]
    if channel in {"Speed", "RPM"} and not flagged.empty:
        fig.add_trace(go.Scatter(x=flagged["Distance"], y=flagged[channel], mode="markers",
                                 name="Potential anomaly", marker={"color": "red", "size": 8},
                                 customdata=flagged[["anomaly_score", "explanation"]],
                                 hovertemplate="Distance %{x:.1f} m<br>Value %{y}<br>Score %{customdata[0]:.2f}<br>%{customdata[1]}<extra></extra>"))
    if not segments.empty:
        fig.add_vrect(x0=distance_low, x1=distance_high, fillcolor="orange", opacity=0.12,
                      line_width=0, layer="below")
    fig.update_layout(title=f"{channel} by distance · {driver} lap {lap_number}",
                      xaxis_title="Distance (m)", yaxis_title=channel)
    st.plotly_chart(fig, width="stretch")

st.subheader("Flagged samples")
flagged = result.samples[result.samples["is_potential_anomaly"]].copy()
if flagged.empty:
    st.info("There are no flagged samples to list for the current method and settings.")
else:
    preferred = [c for c in ["Distance", "Date", "Time", "Speed", "RPM", "Throttle", "Brake", "nGear",
                             "feature_or_channel", "observed_feature_value", "local_reference_value",
                             "anomaly_score", "segment_id", "explanation"] if c in flagged]
    st.dataframe(flagged[preferred], width="stretch", hide_index=True)

sample_export, quality_export, report = telemetry_export_frames(
    result, metadata=metadata, parameters=method_parameters,
)
st.download_button("Download telemetry anomaly samples CSV", sample_export.to_csv(index=False),
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_anomalies.csv", mime="text/csv")
st.download_button("Download telemetry quality CSV", quality_export.to_csv(index=False),
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_quality.csv", mime="text/csv")
st.download_button("Download concise engineering report", report,
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_report.md", mime="text/markdown")
