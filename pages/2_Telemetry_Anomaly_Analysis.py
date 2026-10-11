"""Exploratory anomaly screening for the currently loaded public FastF1 lap."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.lap_comparison import (
    CONTEXT_COLUMNS,
    classify_laps,
    unavailable_lap_markers,
)
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
eligibility = classify_laps(laps)
unavailable_markers = unavailable_lap_markers(laps)
if unavailable_markers:
    st.warning(f"FastF1 did not provide these lap validity markers: {', '.join(unavailable_markers)}. The app cannot filter on missing markers; inspect available lap metadata before interpreting flags.")
eligible = eligibility[eligibility["comparison_eligible"]]
st.caption(f"{len(eligible)} of {len(laps)} lap records meet available timing, accuracy, deletion, and pit-marker checks.")
excluded = eligibility[~eligibility["comparison_eligible"]]
if not excluded.empty:
    with st.expander(f"Excluded laps and reasons ({len(excluded)})"):
        shown = [column for column in (*CONTEXT_COLUMNS, "exclusion_reasons") if column in excluded]
        st.dataframe(excluded[shown], width="stretch", hide_index=True)
lap_options = sorted(eligible["LapNumber"].dropna().astype(int).unique()) if "LapNumber" in eligible else []
if not lap_options:
    st.warning("No lap passed the available timing/validity checks. Select another driver or session; unsuitable laps are listed above.")
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
retrieval = st.session_state.get("f1_retrieval_status", {})
lap_metadata_row = eligible.loc[eligible["LapNumber"] == lap_number].iloc[0]
metadata["lap_conditions"] = {
    column: lap_metadata_row.get(column)
    for column in ("IsAccurate", "Compound", "TyreLife", "Stint", "TrackStatus")
    if column in eligible
}
st.session_state["real_telemetry_anomaly"] = {
    "result": result, "metadata": metadata,
    "parameters": method_parameters,
    "retrieval": retrieval,
}

c1, c2, c3 = st.columns(3)
c1.metric("Usable samples", result.quality["rows_used"])
c2.metric("Potential anomaly samples", result.quality["potential_anomaly_sample_count"])
c3.metric("Contiguous segments", result.quality["potential_anomaly_segment_count"])
st.caption(f"Load completed: {retrieval.get('load_completed_at_utc', 'unavailable')} UTC · cache/network origin: {retrieval.get('cache_origin', 'unknown')} · this timestamp identifies completion, not source provenance.")
st.caption(f"Available channels: {', '.join(result.available_channels)} · Brake and nGear, when present, supply context and are not scored directly.")
st.caption(str(result.quality["method_note"]))
st.info("A sample outlier is a mathematical result, not an engineering concern by itself. Driver inputs, braking, shifts, cornering, tyres, weather, traffic, session type, and data issues may explain unusual public telemetry. FastF1 has no verified anomaly ground truth here; no accuracy, precision, recall, F1, false-positive rate, or failure prediction is available.")
quality_checks = pd.DataFrame([
    {"Check": "Source ordering violations", "Result": result.quality.get("source_ordering_violations", "unavailable")},
    {"Check": "Duplicate distance samples removed", "Result": result.quality.get("duplicate_distance_samples_removed", "unavailable")},
    {"Check": "Invalid distance samples removed", "Result": result.quality.get("invalid_distance_samples_removed", "unavailable")},
    {"Check": "Samples without usable channels removed", "Result": result.quality.get("samples_without_usable_channels_removed", "unavailable")},
    {"Check": "Unscored samples", "Result": result.quality.get("unscored_samples", "unavailable")},
    {"Check": "Distance monotonic after cleanup", "Result": result.quality.get("distance_monotonic_after_cleanup", "unavailable")},
    {"Check": "Warnings", "Result": "; ".join(result.quality.get("warnings", [])) or "None"},
])
st.subheader("Data-quality summary")
st.dataframe(quality_checks.astype({"Result": str}), hide_index=True, width="stretch")

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
    st.caption(f"Selected segment {selected_segment}; review its matching channel chart below. {selected['feature_definition']} Raw source: {selected['raw_channel']} ({selected['raw_channel_unit']}).")
    surrounding = result.samples[
        result.samples["Distance"].between(distance_low, distance_high)
    ].copy()
    surrounding_columns = [column for column in (
        "Distance", "Date", "Time", "Speed", "RPM", "Throttle", "Brake", "nGear",
        "feature_or_channel", "observed_feature_value", "feature_unit",
        "local_reference_value", "contextual_feature_score", "anomaly_score",
        "is_potential_anomaly", "explanation",
    ) if column in surrounding]
    with st.expander(f"Provider and scored samples around segment {selected_segment}"):
        st.caption("Each row is a cleaned FastF1 provider sample. The table keeps original channels beside the transformed feature, its preceding-window reference, and the unitless score.")
        st.dataframe(surrounding[surrounding_columns], width="stretch", hide_index=True)

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
    channel_flags = flagged[flagged["raw_channel"].eq(channel)] if not flagged.empty and "raw_channel" in flagged else flagged.iloc[0:0]
    if not channel_flags.empty:
        fig.add_trace(go.Scatter(x=channel_flags["Distance"], y=channel_flags[channel], mode="markers",
                                 name="Potential anomaly", marker={"color": "red", "size": 8},
                                 customdata=channel_flags[["anomaly_score", "explanation"]],
                                 hovertemplate="Distance %{x:.1f} m<br>Value %{y}<br>Score %{customdata[0]:.2f}<br>%{customdata[1]}<extra></extra>"))
    if not segments.empty:
        fig.add_vrect(x0=distance_low, x1=distance_high, fillcolor="orange", opacity=0.12,
                      line_width=0, layer="below")
    unit = {"Speed": "km/h", "RPM": "rpm", "Throttle": "%", "Brake": "boolean applied", "nGear": "gear number"}.get(channel, channel)
    fig.update_layout(title=f"{channel} by distance · {driver} lap {lap_number}",
                      xaxis_title="Distance (m)", yaxis_title=unit)
    st.plotly_chart(fig, width="stretch")
    if channel_flags.empty:
        observed = values.dropna()
        if channel == "Brake":
            transitions = int(observed.ne(observed.shift()).sum() - (1 if len(observed) else 0))
            detail = f"the brake reading switched between applied and not applied {transitions} times"
        elif channel == "nGear":
            transitions = int(observed.ne(observed.shift()).sum() - (1 if len(observed) else 0))
            detail = f"the selected gear ranged from {observed.min():.0f} to {observed.max():.0f}, with {transitions} gear changes"
        else:
            detail = f"the plotted readings ranged from {observed.min():.1f} to {observed.max():.1f} {unit}"
        st.info(
            f"**No unusual {channel} reading was singled out by this run.** {detail}. "
            "This does not prove that the system is fault-free. For brake use and gear changes, "
            "these are normal driver actions; compare their locations with any flags in other channels."
        )
    else:
        top = channel_flags.loc[channel_flags["anomaly_score"].idxmax()]
        if "Date" in top and pd.notna(top["Date"]):
            timestamp = f" at {top['Date']}"
        elif "Time" in top and pd.notna(top["Time"]):
            timestamp = f" at {top['Time']}"
        else:
            timestamp = ""
        reference = top.get("local_reference_value")
        reference_text = f"{reference:.1f} {top['feature_unit']}" if pd.notna(reference) else "unavailable"
        rule = (f"robust-deviation threshold {top['configured_threshold']:.2f} scale units"
                if method == "Statistical baseline"
                else f"negative decision-function boundary > 0; contamination setting {top['configured_contamination']:.2f}")
        feature_base = str(top["feature_or_channel"]).removesuffix("_change")
        friendly_names = {"Speed": "car speed", "RPM": "engine rotational speed",
                          "Throttle": "throttle pedal position"}
        feature_name = friendly_names.get(feature_base, feature_base)
        raw_value = f"{top['raw_channel_value']:.1f} {top['raw_channel_unit']}"
        if str(top["feature_or_channel"]).endswith("_change"):
            headline = f"A change in {feature_name} was flagged for review near {top['Distance'] / 1000:.1f} km along the lap."
            evidence = (
                f"The {feature_name} changed by {top['observed_feature_value']:.1f} {top['feature_unit']} "
                f"between neighboring recorded readings; recent changes were typically around {reference_text}. "
                f"The plotted {channel.lower()} reading at that point was {raw_value}."
            )
        else:
            headline = f"The {feature_name} reading was flagged for review near {top['Distance'] / 1000:.1f} km along the lap."
            evidence = (
                f"The plotted {feature_name} reading was {raw_value}, compared with recent readings around "
                f"{reference_text}."
            )
        context_values = []
        for column, label, unit, precision in (
            ("Speed", "car speed", "km/h", 0),
            ("RPM", "engine speed", "RPM", 0),
            ("Throttle", "throttle pedal position", "%", 0),
        ):
            value = top.get(column)
            if value is not None and pd.notna(value):
                unit_text = "RPM (engine rotations per minute)" if column == "RPM" else unit
                context_values.append(f"{label} {value:,.{precision}f} {unit_text}")
        brake = top.get("Brake")
        context_values.append(
            f"brake pedal {'used' if bool(brake) else 'not used'}" if brake is not None and pd.notna(brake)
            else "brake reading unavailable"
        )
        gear = top.get("nGear")
        context_values.append(f"gear {gear:.0f}" if gear is not None and pd.notna(gear) else "gear unavailable")
        st.markdown(
            f"**{headline}**  \n"
            f"**Evidence:** {evidence} {timestamp}  \n"
            f"**Nearby readings:** {', '.join(context_values)}.  \n"
            "**Why look closer:** the selected statistical method found this sample unusual compared with nearby observations; unusual does not mean damaged or faulty.  \n"
            "**Next investigation:** inspect the readings immediately before and after this point, then compare a valid lap driven in similar conditions."
        )
        with st.expander(f"Technical Details · {channel} flag", expanded=False):
            st.caption(f"Analysis feature: {top['feature_or_channel']}. {top['feature_definition']}")
            st.write(
                f"Exact point along lap: {top['Distance']:.3f} m. Raw {channel}: {raw_value}. "
                f"Observed feature: {top['observed_feature_value']:.6f} {top['feature_unit']}; "
                f"recent reference: {reference_text}. Score: {top['anomaly_score']:.6f} "
                f"({top['anomaly_score_definition']}); selected rule: {rule}."
            )

st.subheader("Flagged samples")
flagged = result.samples[result.samples["is_potential_anomaly"]].copy()
if flagged.empty:
    st.info("There are no flagged samples to list for the current method and settings.")
else:
    st.caption("The explanation columns distinguish raw channel values, derived feature values and units, the preceding-window feature median, a unitless robust-scale deviation, and the selected model's score/rule. A feature association is descriptive, not causal.")
    preferred = [c for c in ["Distance", "Date", "Time", "Speed", "RPM", "Throttle", "Brake", "nGear",
                             "feature_or_channel", "feature_definition", "feature_unit", "raw_channel",
                             "raw_channel_value", "raw_channel_unit", "observed_feature_value",
                             "local_reference_value", "contextual_feature_score", "anomaly_score",
                             "anomaly_score_definition", "configured_threshold", "configured_contamination",
                             "segment_id", "explanation"] if c in flagged]
    st.dataframe(flagged[preferred], width="stretch", hide_index=True)

sample_export, quality_export, report = telemetry_export_frames(
    result, metadata=metadata, parameters=method_parameters,
    retrieval=retrieval,
)
st.download_button("Download telemetry anomaly samples CSV", sample_export.to_csv(index=False),
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_anomalies.csv", mime="text/csv")
st.download_button("Download telemetry quality CSV", quality_export.to_csv(index=False),
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_quality.csv", mime="text/csv")
st.download_button("Download concise engineering report", report,
                   file_name=f"fastf1_{season}_{driver}_lap{lap_number}_report.md", mime="text/markdown")

with st.expander("Technical Diagnostics", expanded=False):
    st.write("Cache/network origin is unknown; completion timestamps do not establish a cache hit or fresh request.")
    retrieval_diagnostics = dict(retrieval)
    if isinstance(retrieval_diagnostics.get("selected_lap"), dict):
        retrieval_diagnostics["selected_lap"] = {
            key: value for key, value in retrieval_diagnostics["selected_lap"].items()
            if key != "quality"
        }
    st.json({"retrieval": retrieval_diagnostics, "model_parameters": method_parameters, "data_quality": result.quality})
