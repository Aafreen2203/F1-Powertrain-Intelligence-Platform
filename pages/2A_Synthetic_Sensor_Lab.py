"""Optional exploration of clearly labelled synthetic sensor readings."""
import plotly.express as px
import streamlit as st

from src.dashboard_data import cached_synthetic_data

st.title("Synthetic Sensor Lab")
st.warning("SYNTHETIC DATA — illustrative simulated readings, not actual F1 power-unit measurements or genuine failures.")
seed = st.number_input("Reproducible random seed", min_value=0, value=42, step=1)
n_samples = st.slider("Generated records", min_value=200, max_value=1500, value=700, step=100)
data = cached_synthetic_data(n_samples=n_samples, seed=seed)
signal = st.selectbox("Sensor channel", ["temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm"])
signal_names = {
    "temperature_c": ("simulated temperature", "°C", 1),
    "pressure_kpa": ("simulated pressure", "kPa", 1),
    "vibration_mm_s": ("simulated vibration", "mm/s", 2),
    "rotational_speed_rpm": ("simulated engine rotational speed", "RPM", 0),
}
signal_name, unit, precision = signal_names[signal]
unit_explanation = " RPM means rotations per minute.  \n" if unit == "RPM" else ""
fig = px.line(data, x="timestamp", y=signal, color="event_label", title=f"SYNTHETIC · {signal_name}", labels={signal: f"{signal_name.title()} ({unit})", "event_label": "Generated example"})
st.plotly_chart(fig, width="stretch")
st.markdown(
    f"**The {signal_name} ranges from {data[signal].min():.{precision}f} to {data[signal].max():.{precision}f} {unit} in this generated example.**  \n"
    f"{unit_explanation}"
    "**Evidence:** the plotted readings are grouped by generated example type; the event-label table below shows how many readings were assigned to each injected case.  \n"
    "**Context:** these values are generated for demonstration and are not measurements from an F1 car or a real engine.  \n"
    "**Why it matters:** it lets a reader see how the simulated signal changes in cases that were deliberately created for testing.  \n"
    "**Next investigation:** use Model Evaluation to check how well the methods identify those generated cases."
)
st.subheader("Generated event labels")
events = data[data["anomaly_label"].eq(1)].groupby("event_label", as_index=False).agg(records=("anomaly_label", "size"), start=("timestamp", "min"), end=("timestamp", "max"))
st.dataframe(events, width="stretch", hide_index=True)
st.metric("Records with injected labels", f"{int(data['anomaly_label'].sum()):,}")
st.caption("Labels identify generated scenarios only. This page does not diagnose or predict real failures.")
