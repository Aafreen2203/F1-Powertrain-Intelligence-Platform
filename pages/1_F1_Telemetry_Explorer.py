"""On-demand public FastF1 retrieval and distance-aligned lap comparison."""
from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.lap_comparison import (
    LapComparisonError,
    align_laps_by_distance,
    lap_difference_summary,
)
from src.analytics.telemetry import lap_kpis, telemetry_profile
from src.data.fastf1_loader import (
    FastF1DataError,
    list_drivers,
    list_events,
    load_driver_telemetry,
    load_session,
)
from src.validation.quality import validate_frame

st.title("F1 Telemetry Explorer")
st.caption("Public FastF1 data only. Available channels vary; missing real telemetry is never fabricated.")
st.info("Question: how does a driver's speed and RPM behaviour vary across comparable laps, and which deviations deserve further engineering investigation? Differences are descriptive and do not control for tyres, weather, traffic, setup, or track evolution.")
season = st.number_input("Season", min_value=2018, max_value=2100, value=2024, step=1)
session_name = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS", "S"])
if st.button("Load event list", type="primary"):
    try:
        schedule = list_events(int(season))
        name_col = "EventName" if "EventName" in schedule else schedule.columns[0]
        st.session_state["f1_schedule"] = schedule
        st.session_state["f1_event_col"] = name_col
        st.session_state["f1_schedule_season"] = int(season)
        st.success(f"Loaded {len(schedule)} events for {season}.")
    except FastF1DataError as exc:
        for key in ("f1_schedule", "f1_event_col", "f1_schedule_season", "f1_loaded_session", "f1_loaded_key", "f1_telemetry", "real_telemetry_anomaly"):
            st.session_state.pop(key, None)
        st.session_state["f1_retrieval_status"] = {"state": "failed", "error": str(exc)}
        st.error(f"Public event schedule unavailable: {exc}")

schedule = st.session_state.get("f1_schedule")
selected_event = None
if schedule is not None and st.session_state.get("f1_schedule_season") == int(season):
    event_col = st.session_state["f1_event_col"]
    events = schedule[event_col].dropna().astype(str).tolist()
    if events:
        selected_event = st.selectbox("Event", events)
        if st.button("Load / reload selected session"):
            with st.spinner("Retrieving public session data through FastF1…"):
                try:
                    session = load_session(int(season), selected_event, session_name)
                    st.session_state["f1_loaded_session"] = session
                    st.session_state["f1_loaded_key"] = (int(season), selected_event, session_name)
                    st.session_state["f1_retrieval_status"] = {
                        "state": "loaded successfully",
                        "loaded_at_utc": datetime.now(UTC).isoformat(),
                        "cache_origin": "Unknown: FastF1 does not expose whether this result came from network or disk cache through this loader.",
                    }
                    st.session_state.pop("real_telemetry_anomaly", None)
                    st.session_state.pop("anomaly_driver", None)
                    st.session_state.pop("anomaly_lap", None)
                    st.success("Session loaded.")
                except FastF1DataError as exc:
                    for key in ("f1_loaded_session", "f1_loaded_key", "f1_telemetry", "real_telemetry_anomaly"):
                        st.session_state.pop(key, None)
                    st.session_state["f1_retrieval_status"] = {"state": "failed", "error": str(exc)}
                    st.error(f"Session data unavailable: {exc}")
else:
    st.info("Load the event list for the selected season before choosing an event.")

session = st.session_state.get("f1_loaded_session")
loaded_key = st.session_state.get("f1_loaded_key")
if loaded_key != (int(season), selected_event, session_name):
    session = None
    for key in ("f1_loaded_session", "f1_loaded_key", "f1_telemetry", "f1_laps", "real_telemetry_anomaly", "anomaly_driver", "anomaly_lap"):
        st.session_state.pop(key, None)

if session is None:
    st.info("Load an event list, choose an event and session, then request public data. No network request occurs until you press a load button. Use the load button again to explicitly re-request; FastF1 may still serve its disk cache.")
else:
    retrieval = st.session_state.get("f1_retrieval_status", {"state": "loaded; retrieval details unavailable"})
    with st.expander("Retrieval diagnostics", expanded=False):
        st.write("Session data returned successfully. The configured FastF1 cache is enabled; this application cannot reliably classify a successful response as a fresh network fetch or a cache hit.")
        st.json(retrieval)
    drivers = list_drivers(session)
    if not drivers:
        st.warning("The session loaded, but FastF1 returned no driver lap records.")
    else:
        driver = st.selectbox("Driver", drivers, key="explorer_driver")
        laps = session.laps[session.laps["Driver"].astype(str) == driver]
        eligible = laps.dropna(subset=["LapTime"]) if "LapTime" in laps else laps.iloc[0:0]
        if "IsAccurate" in eligible:
            eligible = eligible[eligible["IsAccurate"].fillna(False)]
        for col in ("PitInTime", "PitOutTime"):
            if col in eligible:
                eligible = eligible[eligible[col].isna()]
        if eligible.empty and "LapTime" in laps:
            eligible = laps.dropna(subset=["LapTime"])
            st.warning("No accurate non-pit timed laps were marked; options use timed laps only.")
        lap_options = sorted(eligible["LapNumber"].dropna().astype(int).unique()) if "LapNumber" in eligible else []
        fastest = eligible.sort_values("LapTime")["LapNumber"].dropna().astype(int).tolist() if lap_options else []
        if not lap_options:
            st.warning("No timed lap is available for this driver.")
        else:
            reference_lap = st.selectbox("Reference lap", lap_options, index=lap_options.index(fastest[0]) if fastest else 0, key="explorer_reference_lap")
            comparison_options = [number for number in lap_options if number != reference_lap]
            default_comparison = [number for number in fastest if number != reference_lap][:1]
            comparison_laps = st.multiselect("Comparison lap(s)", comparison_options, default=default_comparison, key="explorer_comparison_laps")
            try:
                reference = load_driver_telemetry(session, driver, lap_number=int(reference_lap))
                st.session_state["f1_telemetry"] = reference
                st.session_state["f1_laps"] = session.laps.copy()
                expected_scoring = {"Speed", "RPM", "Throttle"}
                available_scoring = expected_scoring.intersection(reference.columns)
                telemetry_state = (
                    "partial/incomplete"
                    if "Distance" not in reference or len(reference) < 20 or not available_scoring
                    else "telemetry returned; channel availability varies by session"
                )
                st.session_state["f1_retrieval_status"]["selected_lap"] = {
                    "state": telemetry_state,
                    "driver": driver,
                    "lap": int(reference_lap),
                    "sample_count": len(reference),
                    "available_channels": list(reference.columns),
                }
                st.subheader(f"{driver} · reference lap {reference_lap}")
                st.caption(f"Selected {season} {selected_event} · {session_name} · {driver} · lap {reference_lap}. Loaded into this app at: {retrieval.get('loaded_at_utc', 'unavailable') if isinstance(retrieval, dict) else 'unavailable'}; cache/network origin: unknown.")
                with st.expander("Selected telemetry availability"):
                    st.json(st.session_state["f1_retrieval_status"]["selected_lap"])
                    st.write("Source: public FastF1 telemetry. This app does not classify the result as a fresh fetch or disk-cache hit.")
                has_distance = "Distance" in reference
                if not has_distance:
                    st.warning("This lap has no Distance channel. Lap alignment and distance-based comparison are unavailable; no row-index alignment will be substituted.")
                comparison_data = {}
                failures = {}
                for number in comparison_laps if has_distance else []:
                    try:
                        frame = load_driver_telemetry(session, driver, lap_number=int(number))
                        comparison_data[number] = (frame, align_laps_by_distance(reference, frame))
                    except (FastF1DataError, LapComparisonError) as exc:
                        failures[number] = str(exc)
                if failures:
                    st.warning("Partial comparison: " + "; ".join(f"lap {number}: {error}" for number, error in failures.items()))

                channels = [channel for channel in ("Speed", "RPM", "Throttle", "Brake", "nGear")
                            if channel in reference or any(channel in item[0] for item in comparison_data.values())]
                for channel in channels:
                    fig = go.Figure()
                    x_axis = reference["Distance"] if has_distance else list(range(len(reference)))
                    if channel in reference:
                        fig.add_trace(go.Scatter(x=x_axis, y=reference[channel], mode="lines", name=f"Reference lap {reference_lap}", connectgaps=False))
                    for number, (frame, _) in comparison_data.items():
                        if channel in frame:
                            fig.add_trace(go.Scatter(x=frame["Distance"], y=frame[channel], mode="lines", name=f"Lap {number}", connectgaps=False))
                    fig.update_layout(title=f"{channel} by {'distance' if has_distance else 'provider sample'} · original FastF1 samples", xaxis_title="Distance (m)" if has_distance else "Provider sample (reference lap only)", yaxis_title=channel)
                    st.plotly_chart(fig, width="stretch")
                st.caption("Raw traces preserve each lap's provider samples. For calculated differences, continuous channels are linearly interpolated and brake/gear context uses the nearest sample on a 5 m grid within the shared distance range. Unequal sampling is not row-matched; interpolation may smooth short transients. Time is interpolated against distance where supplied.")

                summaries = []
                for number, (_, aligned) in comparison_data.items():
                    fig = go.Figure()
                    for channel in ("Speed", "RPM"):
                        if f"delta_{channel}" in aligned:
                            fig.add_trace(go.Scatter(x=aligned["Distance"], y=aligned[f"delta_{channel}"], mode="lines", name=f"{channel}: lap {number} minus reference"))
                    fig.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig.update_layout(title=f"Lap {number} minus reference lap {reference_lap} · aligned differences", xaxis_title="Distance (m)", yaxis_title="Channel delta (km/h for Speed; RPM for RPM)")
                    st.plotly_chart(fig, width="stretch")
                    summary = lap_difference_summary(aligned)
                    if not summary.empty:
                        summary.insert(0, "comparison_lap", number)
                        summaries.append(summary)
                if summaries:
                    differences = pd.concat(summaries, ignore_index=True)
                    st.subheader("Largest meaningful channel differences")
                    st.dataframe(differences.sort_values("delta_comparison_minus_reference", key=lambda values: values.abs(), ascending=False), width="stretch", hide_index=True)
                    speed_rows = differences[differences["channel"] == "Speed"].sort_values(
                        "delta_comparison_minus_reference", key=lambda values: values.abs(), ascending=False
                    )
                    if speed_rows.empty:
                        st.info("Speed is not jointly available, so this selection cannot support a speed comparison.")
                    else:
                        finding = speed_rows.iloc[0]
                        aligned = comparison_data[int(finding["comparison_lap"])][1]
                        nearest = aligned.iloc[(aligned["Distance"] - finding["distance_m"]).abs().argmin()]
                        context = []
                        if "reference_Brake" in aligned and "comparison_Brake" in aligned:
                            context.append("brake active on reference lap" if bool(nearest["reference_Brake"]) else "brake inactive on reference lap")
                            context.append("brake active on comparison lap" if bool(nearest["comparison_Brake"]) else "brake inactive on comparison lap")
                        if "reference_nGear" in aligned and "comparison_nGear" in aligned:
                            context.append("gear differs between laps" if nearest["reference_nGear"] != nearest["comparison_nGear"] else "gear matches between laps")
                        context_text = "; ".join(context) if context else "brake or gear context is unavailable for both laps"
                        st.subheader("Engineering Interpretation")
                        time_context = ""
                        if pd.notna(finding.get("reference_time_s")) and pd.notna(finding.get("comparison_time_s")):
                            time_context = f" At this distance the interpolated times are {finding['reference_time_s']:.2f} s and {finding['comparison_time_s']:.2f} s."
                        observation = (
                            "No measurable speed difference is present on the aligned grid."
                            if abs(finding["delta_comparison_minus_reference"]) < 1e-9
                            else f"The largest absolute speed difference in the selected comparison is {finding['delta_comparison_minus_reference']:+.1f} km/h (comparison minus reference)."
                        )
                        st.markdown(
                            f"**Observation:** {observation}\n\n"
                            f"**Location:** {finding['distance_m']:.0f} m.\n\n"
                            f"**Evidence:** Reference {finding['reference_value']:.1f} km/h; comparison {finding['comparison_value']:.1f} km/h. {context_text}.{time_context}\n\n"
                            "**Context:** Speed changes can reflect braking, acceleration, cornering, driver inputs, tyres, weather, traffic, setup, or session evolution; public signals do not isolate these causes.\n\n"
                            "**Confidence and limitations:** This is an interpolated two-lap observation, not a fault diagnosis. Check whether it persists across settings and laps.\n\n"
                            "**Suggested next investigation:** Inspect the preserved raw traces, sector timing, tyre/weather context, and suitable authorised engineering measurements before drawing a conclusion."
                        )
                elif comparison_laps and has_distance:
                    st.info("The selected laps did not produce shared analyzable continuous channels.")
                elif comparison_laps and not has_distance:
                    st.info("Selected laps were not compared because distance alignment is unavailable.")
                else:
                    st.info("Select one or more comparison laps to calculate distance-aligned differences.")

                profile = telemetry_profile(reference)
                st.caption(f"{profile['record_count']} reference samples. Available provider channels: {', '.join(profile['available_columns'])}")
                if "LapTime" in laps:
                    st.subheader("Driver lap summary")
                    st.dataframe(lap_kpis(laps, group_by="Driver"), width="stretch", hide_index=True)
                    cols = [col for col in ("LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "Compound", "TyreLife") if col in laps]
                    st.dataframe(laps[cols].sort_values("LapNumber"), width="stretch", hide_index=True)
                st.subheader("Reference telemetry data quality")
                st.json(validate_frame(reference, timestamp_col="Date" if "Date" in reference else None))
                st.caption("FastF1 public telemetry may provide speed, RPM, throttle, braking, and gear but does not expose a team's complete internal power-unit measurements. Synthetic temperature, pressure, vibration, and RPM signals on the separate lab page are simulated, not F1 measurements. A flagged segment is an investigation prompt, not a diagnosis; verified fault labels, reference measurements, engineering context, or authorised internal sensor data could strengthen the analysis.")
            except FastF1DataError as exc:
                st.session_state.pop("f1_telemetry", None)
                st.warning(f"Telemetry unavailable for this driver/lap: {exc}")
