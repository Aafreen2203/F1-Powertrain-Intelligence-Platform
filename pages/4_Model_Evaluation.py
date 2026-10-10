"""Evaluate synthetic detection methods on a later time block."""
import plotly.express as px
import streamlit as st

from src.dashboard_data import cached_synthetic_data
from src.models.anomaly import evaluate_anomaly_methods

st.title("Model Evaluation")
st.warning("Synthetic benchmark only. Scores do not describe real power-unit fault detection.")
seed = st.number_input("Data seed", min_value=0, value=42, step=1)
test_fraction = st.slider("Later holdout fraction", min_value=0.2, max_value=0.5, value=0.3, step=0.05)
threshold = st.slider("Baseline robust-z threshold", min_value=1.0, max_value=8.0, value=3.5, step=0.25)
contamination = st.slider("Isolation Forest contamination setting", min_value=0.01, max_value=0.2, value=0.05, step=0.01)
data = cached_synthetic_data(seed=seed)
features = ["temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm"]
try:
    result = evaluate_anomaly_methods(data, feature_cols=features, test_fraction=test_fraction, threshold=threshold, contamination=contamination, random_state=42)
    st.caption(f"Chronological split at row {result.split_index}; fitted using {result.train_normal_count} known-normal records in the earlier block. Labels are excluded from features.")
    display_metrics = result.metrics.assign(dataset_type="SYNTHETIC · illustrative sensor benchmark")
    st.dataframe(display_metrics, width="stretch", hide_index=True)
    metric_name = st.selectbox("Metric chart", ["precision", "recall", "f1", "false_positive_rate"])
    st.plotly_chart(px.bar(result.metrics, x="model", y=metric_name, range_y=[0, 1], title=f"SYNTHETIC · {metric_name.replace('_', ' ').title()}"), width="stretch")
    st.subheader("Held-out flag review")
    flags = result.predictions[result.predictions["baseline_flag"].eq(1) | result.predictions["isolation_forest_flag"].eq(1)]
    st.dataframe(flags.head(100), width="stretch", hide_index=True)
except (ValueError, ImportError) as exc:
    st.error(f"Could not evaluate models: {exc}")
st.markdown("**Metrics:** precision is the share of flags matching injected labels; recall is the share of injected records found; F1 balances precision and recall; false-positive rate is the share of normal holdout records flagged. See `docs/analytics-and-modeling.md` for definitions and limitations. The clean-normal training assumption is favorable; Isolation Forest contamination is not a measured fault prevalence. Flags are anomaly indicators, not diagnosis or failure prediction.")
