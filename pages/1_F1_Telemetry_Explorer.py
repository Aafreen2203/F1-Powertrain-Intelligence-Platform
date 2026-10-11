"""On-demand public FastF1 retrieval and distance-aligned lap comparison."""
from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analytics.lap_comparison import (
    CONTEXT_COLUMNS,
    LapComparisonError,
    align_laps_by_distance,
    classify_laps,
    lap_difference_summary,
    lap_weather_at_midpoint,
    unavailable_lap_markers,
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
                    requested_at = datetime.now(UTC).isoformat()
                    session = load_session(int(season), selected_event, session_name)
                    st.session_state["f1_loaded_session"] = session
                    st.session_state["f1_loaded_key"] = (int(season), selected_event, session_name)
                    st.session_state["f1_retrieval_status"] = {
                        "state": "loaded successfully",
                        "load_requested_at_utc": requested_at,
                        "load_completed_at_utc": datetime.now(UTC).isoformat(),
                        "cache_origin": "unknown; the loader/FastF1 call does not expose reliable per-request provenance",
                    }
                    st.session_state.pop("f1_lap_comparison", None)
                    st.session_state.pop("real_telemetry_anomaly", None)
                    st.session_state.pop("anomaly_driver", None)
                    st.session_state.pop("anomaly_lap", None)
                    st.success("Session loaded.")
                except FastF1DataError as exc:
                    for key in ("f1_loaded_session", "f1_loaded_key", "f1_telemetry", "real_telemetry_anomaly", "f1_lap_comparison"):
                        st.session_state.pop(key, None)
                    st.session_state["f1_retrieval_status"] = {"state": "failed", "error": str(exc)}
                    st.error(f"Session data unavailable: {exc}")
else:
    st.info("Load the event list for the selected season before choosing an event.")

session = st.session_state.get("f1_loaded_session")
loaded_key = st.session_state.get("f1_loaded_key")
if loaded_key != (int(season), selected_event, session_name):
    session = None
    for key in ("f1_loaded_session", "f1_loaded_key", "f1_telemetry", "f1_laps", "real_telemetry_anomaly", "f1_lap_comparison", "anomaly_driver", "anomaly_lap"):
        st.session_state.pop(key, None)

if session is None:
    st.info("Load an event list, choose an event and session, then request public data. No network request occurs until you press a load button. Use the load button again to explicitly re-request; FastF1 may still serve its disk cache.")
else:
    retrieval = st.session_state.get("f1_retrieval_status", {"state": "loaded; retrieval details unavailable"})
    drivers = list_drivers(session)
    if not drivers:
        st.warning("The session loaded, but FastF1 returned no driver lap records.")
    else:
        driver = st.selectbox("Driver", drivers, key="explorer_driver")
        prior_comparison = st.session_state.get("f1_lap_comparison")
        if prior_comparison and prior_comparison["metadata"].get("driver") != driver:
            st.session_state.pop("f1_lap_comparison", None)
        laps = session.laps[session.laps["Driver"].astype(str) == driver]
        eligibility = classify_laps(laps)
        unavailable_markers = unavailable_lap_markers(laps)
        if unavailable_markers:
            st.warning(f"FastF1 did not provide these lap validity markers: {', '.join(unavailable_markers)}. The app cannot filter on missing markers; review the displayed available metadata before interpreting comparisons.")
        eligible = eligibility[eligibility["comparison_eligible"]]
        st.caption(f"{len(eligible)} of {len(laps)} driver lap records meet available timing, accuracy, deletion, and pit-marker checks.")
        excluded = eligibility[~eligibility["comparison_eligible"]]
        if not excluded.empty:
            with st.expander(f"Excluded laps and reasons ({len(excluded)})", expanded=False):
                shown = [column for column in (*CONTEXT_COLUMNS, "exclusion_reasons") if column in excluded]
                st.dataframe(excluded[shown], width="stretch", hide_index=True)
        lap_options = sorted(eligible["LapNumber"].dropna().astype(int).unique()) if "LapNumber" in eligible else []
        fastest = eligible.sort_values("LapTime")["LapNumber"].dropna().astype(int).tolist() if lap_options else []
        if not lap_options:
            st.warning("No lap passed the available timing/validity checks. Select another driver or session; unsuitable laps are listed above.")
        else:
            reference_lap = st.selectbox("Reference lap", lap_options, index=lap_options.index(fastest[0]) if fastest else 0, key="explorer_reference_lap")
            comparison_options = [number for number in lap_options if number != reference_lap]
            default_comparison = [number for number in fastest if number != reference_lap][:1]
            comparison_laps = st.multiselect("Comparison lap(s)", comparison_options, default=default_comparison, key="explorer_comparison_laps")
            st.session_state.pop("f1_lap_comparison", None)
            selected_lap_rows = eligible[eligible["LapNumber"].isin([reference_lap, *comparison_laps])]
            context_rows = []
            for _, lap_row in selected_lap_rows.iterrows():
                item = {column: lap_row.get(column) for column in CONTEXT_COLUMNS if column in selected_lap_rows}
                item["comparison_role"] = "reference" if lap_row["LapNumber"] == reference_lap else "comparison"
                weather = lap_weather_at_midpoint(getattr(session, "weather_data", pd.DataFrame()), lap_row)
                for column in ("AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindSpeed"):
                    item[f"midlap_{column}"] = weather.get(column) if weather is not None and column in weather else None
                item["weather_sample_offset_s"] = weather.get("lap_midpoint_offset_seconds") if weather is not None else None
                context_rows.append(item)
            lap_context = pd.DataFrame(context_rows)
            if not lap_context.empty:
                st.subheader("Lap validity and conditions")
                st.caption("Laps are filtered using FastF1 timing, accuracy, deletion, and pit markers where those fields exist. Compound, stint, track status, and nearest session-weather samples provide context; differences are warnings, not automatic exclusions.")
                st.dataframe(lap_context, width="stretch", hide_index=True)
                for condition in ("Compound", "Stint", "TrackStatus"):
                    if condition in lap_context and lap_context[condition].nunique(dropna=False) > 1:
                        st.warning(f"Selected laps differ in {condition}; interpret the comparison in that context.")
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
                    "quality": validate_frame(reference, timestamp_col="Date" if "Date" in reference else None),
                    "analysis_completed_at_utc": datetime.now(UTC).isoformat(),
                }
                st.subheader(f"{driver} · reference lap {reference_lap}")
                st.caption(f"Selected {season} {selected_event} · {session_name} · {driver} · lap {reference_lap}. Session load completed at {retrieval.get('load_completed_at_utc', 'unavailable') if isinstance(retrieval, dict) else 'unavailable'} UTC; telemetry selection/quality completed at {st.session_state['f1_retrieval_status']['selected_lap']['analysis_completed_at_utc']} UTC. Cache/network origin: unknown.")
                quality = st.session_state["f1_retrieval_status"]["selected_lap"]["quality"]
                quality_rows = [
                    {"Check": "Records", "Result": quality.get("record_count", "unavailable")},
                    {"Check": "Columns", "Result": quality.get("column_count", "unavailable")},
                    {"Check": "Missing cells", "Result": sum(quality.get("missing_counts", {}).values())},
                    {"Check": "Duplicate records", "Result": quality.get("duplicate_records", "unavailable")},
                    {"Check": "Validation", "Result": "Passed" if quality.get("passed") else "Review"},
                ]
                st.dataframe(pd.DataFrame(quality_rows).astype({"Result": str}), hide_index=True, width="stretch")
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

                summaries = []
                for number, (_, aligned) in comparison_data.items():
                    summary = lap_difference_summary(aligned)
                    if not summary.empty:
                        summary.insert(0, "comparison_lap", number)
                        summaries.append(summary)
                differences = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
                unit_by_channel = {"Speed": "km/h", "RPM": "rpm", "Throttle": "percentage points"}

                def finding_for(channel):
                    if differences.empty:
                        return None
                    rows = differences[differences["channel"] == channel]
                    if rows.empty:
                        return None
                    return rows.loc[rows["delta_comparison_minus_reference"].abs().idxmax()]

                def comparison_context(finding):
                    aligned = comparison_data[int(finding["comparison_lap"])][1]
                    nearest = aligned.iloc[(aligned["Distance"] - finding["distance_m"]).abs().argmin()]
                    values = []
                    for name, unit in (("Speed", "km/h"), ("RPM", "rpm"), ("Throttle", "%")):
                        ref, comp = f"reference_{name}", f"comparison_{name}"
                        if ref in aligned and comp in aligned and pd.notna(nearest[ref]) and pd.notna(nearest[comp]):
                            values.append(f"{name} {nearest[ref]:.1f}/{nearest[comp]:.1f} {unit} (reference/comparison)")
                    if "reference_Brake" in aligned and "comparison_Brake" in aligned:
                        values.append(f"brake {bool(nearest['reference_Brake'])}/{bool(nearest['comparison_Brake'])}")
                    if "reference_nGear" in aligned and "comparison_nGear" in aligned:
                        values.append(f"gear {nearest['reference_nGear']}/{nearest['comparison_nGear']}")
                    return "; ".join(values) or "No other aligned channels are available at this location."

                channels = [channel for channel in ("Speed", "RPM", "Throttle", "Brake", "nGear")
                            if channel in reference or any(channel in item[0] for item in comparison_data.values())]
                for channel in channels:
                    fig = go.Figure()
                    x_axis = reference["Distance"] if has_distance else list(range(len(reference)))
                    unit = {"Speed": "km/h", "RPM": "rpm", "Throttle": "%", "Brake": "boolean applied", "nGear": "gear"}.get(channel, channel)
                    line_shape = "hv" if channel in {"Brake", "nGear"} else "linear"
                    if channel in reference:
                        fig.add_trace(go.Scatter(x=x_axis, y=reference[channel], mode="lines", name=f"Reference lap {reference_lap}", connectgaps=False, line_shape=line_shape))
                    for number, (frame, _) in comparison_data.items():
                        if channel in frame:
                            fig.add_trace(go.Scatter(x=frame["Distance"], y=frame[channel], mode="lines", name=f"Lap {number}", connectgaps=False, line_shape=line_shape))
                    fig.update_layout(title=f"{channel} by {'distance' if has_distance else 'provider sample'} · original FastF1 samples", xaxis_title="Distance (m)" if has_distance else "Provider sample (reference lap only)", yaxis_title=unit)
                    st.plotly_chart(fig, width="stretch")
                    if channel in unit_by_channel:
                        finding = finding_for(channel)
                        if finding is None:
                            st.info(f"**Engineering Review · {channel}:** no finite aligned comparison values are available for this channel.")
                        else:
                            st.markdown(
                                f"**Engineering Review · {channel}**  \n"
                                f"**Observation:** largest absolute difference is {finding['delta_comparison_minus_reference']:+.2f} {unit_by_channel[channel]} at {finding['distance_m']:.1f} m.  \n"
                                f"**Evidence:** reference {finding['reference_value']:.2f}; lap {int(finding['comparison_lap'])} {finding['comparison_value']:.2f}; sign is comparison minus reference. Coverage {finding['valid_aligned_samples']}/{finding['aligned_grid_samples']} ({finding['coverage_fraction']:.1%}).  \n"
                                f"**Context:** {comparison_context(finding)}. This measured difference does not isolate braking, acceleration, cornering, or a fault.  \n"
                                f"**Next investigation:** compare the adjacent RPM, throttle, brake, and gear traces and review another condition-matched lap."
                            )
                    elif channel in {"Brake", "nGear"}:
                        context_frames = [(reference_lap, reference), *[(number, pair[0]) for number, pair in comparison_data.items()]]
                        transition_summary = []
                        for lap_id, frame in context_frames:
                            if channel not in frame:
                                continue
                            values = frame[channel].dropna()
                            transitions = int(values.ne(values.shift()).sum() - (1 if len(values) else 0))
                            transition_summary.append(f"lap {lap_id}: {transitions} state/gear transitions")
                        st.markdown(
                            f"**Engineering Review · {channel}**  \n"
                            f"**Observation:** {('; '.join(transition_summary) or 'channel unavailable')}.  \n"
                            f"**Context:** brake application and gear changes are normal driver/control behaviour; this view alone does not indicate a fault.  \n"
                            f"**Next investigation:** compare transition locations with the aligned speed and RPM traces."
                        )
                st.caption("Raw traces preserve each lap's provider samples. For calculated differences, continuous channels are linearly interpolated and brake/gear context uses the nearest sample on a 5 m grid within the shared distance range. Unequal sampling is not row-matched; interpolation may smooth short transients. Time is interpolated against distance where supplied.")

                for number, (_, aligned) in comparison_data.items():
                    delta_channels = [channel for channel in ("Speed", "RPM", "Throttle")
                                      if f"delta_{channel}" in aligned]
                    if delta_channels:
                        fig = make_subplots(
                            rows=len(delta_channels), cols=1, shared_xaxes=True,
                            vertical_spacing=0.08, subplot_titles=delta_channels,
                        )
                        for row_index, channel in enumerate(delta_channels, start=1):
                            fig.add_trace(
                                go.Scatter(x=aligned["Distance"], y=aligned[f"delta_{channel}"],
                                           mode="lines", name=f"Lap {number} minus reference",
                                           connectgaps=False),
                                row=row_index, col=1,
                            )
                            fig.add_hline(y=0, line_dash="dash", line_color="gray", row=row_index, col=1)
                            unit = {"Speed": "km/h", "RPM": "rpm", "Throttle": "percentage points"}[channel]
                            fig.update_yaxes(title_text=unit, row=row_index, col=1)
                        fig.update_xaxes(title_text="Distance (m)", row=len(delta_channels), col=1)
                        fig.update_layout(title=f"Lap {number} minus reference lap {reference_lap} · distance-aligned differences", height=max(360, 230 * len(delta_channels)))
                        st.plotly_chart(fig, width="stretch")
                        chart_rows = differences[differences["comparison_lap"].eq(number)] if not differences.empty else pd.DataFrame()
                        if chart_rows.empty:
                            st.info("**Engineering Review:** no finite aligned differences are available in this chart.")
                        else:
                            notes = [
                                f"**{row.channel}:** {row.delta_comparison_minus_reference:+.2f} {unit_by_channel[row.channel]} at {row.distance_m:.1f} m (comparison minus reference; {row.valid_aligned_samples}/{row.aligned_grid_samples} finite grid points)"
                                for row in chart_rows.itertuples() if row.channel in unit_by_channel
                            ]
                            st.markdown("**Engineering Review · distance-aligned differences**  \n" + "  \n".join(notes) + "  \nThese are observed differences; braking, shifts, and other conditions are context, not established causes.")
                    else:
                        st.info(f"Lap {number} shares no continuous Speed, RPM, or Throttle channel for a difference trace.")
                if not differences.empty:
                    st.subheader("Largest meaningful channel differences")
                    st.caption("For each selected comparison and continuous shared channel, this reports the maximum absolute aligned difference, its sign (comparison minus reference), and the fraction of shared-grid samples with finite values. Low-speed corners are retained as valid track observations; pit/inaccurate/deleted laps are excluded by available explicit markers.")
                    st.dataframe(differences.sort_values("delta_comparison_minus_reference", key=lambda values: values.abs(), ascending=False), width="stretch", hide_index=True)
                    comparison_metadata = {
                        "year": season, "event": selected_event, "session": session_name,
                        "driver": driver, "reference_lap": int(reference_lap),
                        "comparison_laps": [int(number) for number in comparison_data],
                        "retrieval": retrieval,
                        "lap_context": lap_context.to_dict(orient="records"),
                        "telemetry_quality": {
                            str(int(reference_lap)): validate_frame(
                                reference, timestamp_col="Date" if "Date" in reference else None
                            ),
                            **{
                                str(int(number)): validate_frame(
                                    frame, timestamp_col="Date" if "Date" in frame else None
                                )
                                for number, (frame, _) in comparison_data.items()
                            },
                        },
                        "alignment_method": "5 m shared distance grid; linear interpolation for continuous channels, nearest source sample for Brake/nGear; no extrapolation across missing neighbours",
                    }
                    st.session_state["f1_lap_comparison"] = {
                        "metadata": comparison_metadata,
                        "summary": differences.copy(),
                        "aligned": {number: aligned.copy() for number, (_, aligned) in comparison_data.items()},
                    }
                elif not comparison_laps:
                    st.session_state.pop("f1_lap_comparison", None)
                    st.info("Choose at least one eligible comparison lap to build the case study.")
                else:
                    st.session_state.pop("f1_lap_comparison", None)
                    st.info("No finite shared continuous channels are available for this selection. Review the available columns or choose another clean lap.")
                profile = telemetry_profile(reference)
                st.caption(f"{profile['record_count']} reference samples. Available provider channels: {', '.join(profile['available_columns'])}")
                if "LapTime" in laps:
                    st.subheader("Driver lap summary")
                    st.dataframe(lap_kpis(laps, group_by="Driver"), width="stretch", hide_index=True)
                    cols = [col for col in ("LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "Compound", "TyreLife") if col in laps]
                    st.dataframe(laps[cols].sort_values("LapNumber"), width="stretch", hide_index=True)
                st.subheader("Reference telemetry data quality")
                st.caption("Public FastF1 samples are shown as retrieved. Missing values and channel limits are summarized above; no internal power-unit sensors or fault labels are available.")
                with st.expander("Technical Diagnostics", expanded=False):
                    st.write("The completion timestamp records when FastF1 returned; cache/network origin remains unknown.")
                    retrieval_diagnostics = dict(st.session_state.get("f1_retrieval_status", {}))
                    if isinstance(retrieval_diagnostics.get("selected_lap"), dict):
                        retrieval_diagnostics["selected_lap"] = {
                            key: value for key, value in retrieval_diagnostics["selected_lap"].items()
                            if key != "quality"
                        }
                    st.json({"retrieval": retrieval_diagnostics, "reference_telemetry_quality": quality})
                st.caption("FastF1 public telemetry may provide speed, RPM, throttle, braking, and gear but does not expose a team's complete internal power-unit measurements. Synthetic temperature, pressure, vibration, and RPM signals on the separate lab page are simulated, not F1 measurements. A flagged segment is an investigation prompt, not a diagnosis; verified fault labels, reference measurements, engineering context, or authorised internal sensor data could strengthen the analysis.")
            except FastF1DataError as exc:
                st.session_state.pop("f1_telemetry", None)
                st.warning(f"Telemetry unavailable for this driver/lap: {exc}")
