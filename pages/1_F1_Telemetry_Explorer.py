"""On-demand public FastF1 session and telemetry explorer."""
import pandas as pd
import plotly.express as px
import streamlit as st

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
st.info("Comparisons are descriptive and do not control for tyres, weather, traffic, setup, or track evolution.")
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
        st.session_state.pop("f1_schedule", None)
        st.session_state.pop("f1_event_col", None)
        st.session_state.pop("f1_schedule_season", None)
        st.session_state.pop("f1_loaded_session", None)
        st.session_state.pop("f1_loaded_key", None)
        st.session_state.pop("f1_telemetry", None)
        st.session_state.pop("real_telemetry_anomaly", None)
        st.error(f"Public event schedule unavailable: {exc}")

schedule = st.session_state.get("f1_schedule")
selected_event = None
if schedule is not None and st.session_state.get("f1_schedule_season") == int(season):
    event_col = st.session_state["f1_event_col"]
    events = schedule[event_col].dropna().astype(str).tolist()
    if events:
        event = st.selectbox("Event", events)
        selected_event = event
        if st.button("Load selected session"):
            with st.spinner("Retrieving public session data via FastF1…"):
                try:
                    session = load_session(int(season), event, session_name)
                    st.session_state["f1_loaded_session"] = session
                    st.session_state["f1_loaded_key"] = (int(season), event, session_name)
                    st.session_state.pop("real_telemetry_anomaly", None)
                    st.session_state.pop("anomaly_driver", None)
                    st.session_state.pop("anomaly_lap", None)
                    st.success("Session loaded.")
                except FastF1DataError as exc:
                    st.session_state.pop("f1_loaded_session", None)
                    st.session_state.pop("f1_loaded_key", None)
                    st.session_state.pop("f1_telemetry", None)
                    st.session_state.pop("real_telemetry_anomaly", None)
                    st.error(f"Session data unavailable: {exc}")
else:
    st.info("Load the event list for the selected season before choosing an event.")

session = st.session_state.get("f1_loaded_session")
loaded_key = st.session_state.get("f1_loaded_key")
if loaded_key != (int(season), selected_event, session_name):
    session = None
    st.session_state.pop("f1_loaded_session", None)
    st.session_state.pop("f1_loaded_key", None)
    st.session_state.pop("f1_telemetry", None)
    st.session_state.pop("f1_laps", None)
    st.session_state.pop("real_telemetry_anomaly", None)
    st.session_state.pop("anomaly_driver", None)
    st.session_state.pop("anomaly_lap", None)
if session is not None:
    drivers = list_drivers(session)
    if not drivers:
        st.warning("The session loaded, but FastF1 returned no driver lap records.")
    else:
        driver = st.selectbox("Driver", drivers)
        laps = session.laps[session.laps["Driver"].astype(str) == driver]
        eligible_laps = laps.dropna(subset=["LapTime"]) if "LapTime" in laps else laps.iloc[0:0]
        if "IsAccurate" in eligible_laps:
            eligible_laps = eligible_laps[eligible_laps["IsAccurate"].fillna(False)]
        if "PitInTime" in eligible_laps:
            eligible_laps = eligible_laps[eligible_laps["PitInTime"].isna()]
        if "PitOutTime" in eligible_laps:
            eligible_laps = eligible_laps[eligible_laps["PitOutTime"].isna()]
        # If provider quality flags leave no laps, retain timed laps and disclose
        # the weaker selection instead of making the explorer unusable.
        if eligible_laps.empty and "LapTime" in laps:
            eligible_laps = laps.dropna(subset=["LapTime"])
            st.warning("No accurate non-pit timed laps were marked by FastF1; lap options use timed laps only.")
        lap_options = sorted(eligible_laps["LapNumber"].dropna().astype(int).unique().tolist()) if "LapNumber" in eligible_laps else []
        fastest_options = eligible_laps.sort_values("LapTime")["LapNumber"].dropna().astype(int).tolist() if lap_options else []
        fastest_lap = fastest_options[0] if fastest_options else None
        lap_number = st.selectbox("Lap for telemetry", lap_options, index=lap_options.index(fastest_lap)) if lap_options else None
        comparison_options = lap_options
        comparison_default = list(dict.fromkeys(fastest_options[:2]))
        compared_laps = st.multiselect("Laps to compare", comparison_options, default=comparison_default) if comparison_options else []
        try:
            telemetry = load_driver_telemetry(session, driver, lap_number=lap_number)
            st.session_state["f1_telemetry"] = telemetry
            st.session_state["f1_laps"] = session.laps.copy()
            st.subheader(f"{driver} · available telemetry channels")
            numeric = telemetry.select_dtypes(include="number").select_dtypes(
                exclude=["timedelta", "datetime"]
            ).columns.tolist()
            if numeric:
                signal_default = numeric.index("Speed") if "Speed" in numeric else 0
                signal = st.selectbox("Signal", numeric, index=signal_default)
                x_options = [c for c in ["Distance", "Time"] if c in telemetry]
                x_col = st.selectbox("Horizontal axis", x_options) if x_options else "Sample"
                plot_data = telemetry.reset_index(drop=True)
                if x_col == "Sample":
                    plot_data[x_col] = range(len(plot_data))
                plot_frames = []
                for number in compared_laps:
                    try:
                        lap_data = load_driver_telemetry(session, driver, lap_number=int(number)).reset_index(drop=True)
                        if signal not in lap_data:
                            continue
                        axis = x_col if x_col in lap_data else "Sample"
                        if axis == "Sample":
                            lap_data[axis] = range(len(lap_data))
                        else:
                            lap_data = lap_data.sort_values(axis, kind="stable")
                        lap_data["Lap"] = f"Lap {number}"
                        plot_frames.append(lap_data[[axis, signal, "Lap"]])
                    except FastF1DataError:
                        continue
                chart_data = pd.concat(plot_frames, ignore_index=True) if plot_frames else plot_data.assign(Lap=f"Lap {lap_number}")
                st.caption("Lap traces use their own provider samples on the shared distance axis; samples are not interpolated or row-matched.")
                chart_x = x_col if x_col in chart_data else "Sample"
                st.plotly_chart(px.line(chart_data, x=chart_x, y=signal, color="Lap", title=f"{signal} · {driver} lap comparison"), width="stretch")
                profile = telemetry_profile(telemetry)
                st.caption(f"{profile['record_count']} records. Provider channels: {', '.join(profile['available_columns'])}")
            else:
                st.warning("Telemetry contains no numeric channels to plot.")
            if "LapTime" in laps:
                st.subheader("Driver lap summary")
                st.dataframe(lap_kpis(laps, group_by="Driver"), width="stretch", hide_index=True)
                comparison_cols = [c for c in ["LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "Compound", "TyreLife"] if c in laps]
                st.caption("Available lap and sector timing comparison for this driver.")
                st.dataframe(laps[comparison_cols].sort_values("LapNumber"), width="stretch", hide_index=True)
            st.subheader("Telemetry data quality")
            st.json(validate_frame(telemetry, timestamp_col="Date" if "Date" in telemetry else None))
        except FastF1DataError as exc:
            st.session_state.pop("f1_telemetry", None)
            st.warning(f"Telemetry unavailable for this driver/lap: {exc}")
else:
    st.info("Load an event list, choose an event and session, then request public data. No network request occurs until you press a load button.")
