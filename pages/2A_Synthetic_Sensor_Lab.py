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
fig = px.line(data, x="timestamp", y=signal, color="event_label", title=f"SYNTHETIC · {signal}", labels={"event_label": "Injected scenario"})
st.plotly_chart(fig, width="stretch")
st.markdown(
    f"**Engineering Review · synthetic {signal}**  \n"
    f"**Observation:** the chart shows simulated {signal} grouped by injected scenario.  \n"
    f"**Evidence:** generated values span {data[signal].min():.2f} to {data[signal].max():.2f}; scenario counts are shown below.  \n"
    "**Context:** these are seeded illustrative sensor readings, not FastF1 channels or measured engine behaviour.  \n"
    "**Next investigation:** use Model Evaluation to compare synthetic flags against the injected labels."
)
st.subheader("Generated event labels")
events = data[data["anomaly_label"].eq(1)].groupby("event_label", as_index=False).agg(records=("anomaly_label", "size"), start=("timestamp", "min"), end=("timestamp", "max"))
st.dataframe(events, width="stretch", hide_index=True)
st.metric("Records with injected labels", f"{int(data['anomaly_label'].sum()):,}")
st.caption("Labels identify generated scenarios only. This page does not diagnose or predict real failures.")
