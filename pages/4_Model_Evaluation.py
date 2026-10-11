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
    st.caption("Earlier simulated readings train the methods; later readings test them. Simulated event labels are kept separate from the readings given to the methods.")
    metric_labels = {
        "precision": "Correctness of flagged readings",
        "recall": "Share of generated events found",
        "f1": "Combined balance score",
        "false_positive_rate": "Ordinary readings incorrectly flagged",
    }
    metric_name = st.selectbox("Choose what to compare", list(metric_labels), format_func=metric_labels.get)
    metric_help = {
        "precision": "When a method flagged a simulated reading, how often it coincided with an injected event",
        "recall": "How much of the injected simulated activity the method found",
        "f1": "A combined score balancing how often flags were right and how much injected activity was found",
        "false_positive_rate": "How often ordinary simulated readings were incorrectly flagged",
    }
    metric_plain_names = {
        "precision": "correctness of flagged readings",
        "recall": "share of simulated events found",
        "f1": "combined score balancing correct flags and events found",
        "false_positive_rate": "rate of ordinary readings incorrectly flagged",
    }
    method_names = {
        "Statistical robust-z baseline": "Statistical comparison",
        "Isolation Forest": "Unusual-pattern method",
    }
    chart_metrics = result.metrics.copy()
    chart_metrics["review_method"] = chart_metrics["model"].map(method_names).fillna(chart_metrics["model"])
    chart_metrics["result_percent"] = chart_metrics[metric_name] * 100
    st.plotly_chart(px.bar(
        chart_metrics, x="review_method", y="result_percent", range_y=[0, 100],
        title=f"SYNTHETIC · {metric_labels[metric_name]}",
        labels={"review_method": "Method", "result_percent": "Share of test readings (%)"},
    ), width="stretch")
    if result.metrics.empty:
        st.info("There are not enough evaluated readings to produce a dependable model comparison.")
    else:
        lower_is_better = metric_name == "false_positive_rate"
        best = result.metrics.sort_values(metric_name, ascending=lower_is_better).iloc[0]
        method_label = method_names.get(best["model"], best["model"])
        score_percent = best[metric_name] * 100
        comparison = result.metrics[["model", metric_name]].copy()
        comparison["Method"] = comparison["model"].map(method_names).fillna(comparison["model"])
        comparison["Result"] = comparison[metric_name].map(lambda value: f"{value:.0%}")
        comparison_table = comparison[["Method", "Result"]]
        if result.metrics[metric_name].nunique() == 1:
            headline = f"Both methods had the same {metric_plain_names[metric_name]} in this simulated test: {score_percent:.0f}%."
        elif lower_is_better:
            headline = f"The {method_label.lower()} had the lower {metric_plain_names[metric_name]}: {score_percent:.0f}%."
        else:
            headline = f"The {method_label.lower()} had the higher {metric_plain_names[metric_name]} in this simulated test: {score_percent:.0f}%."
        st.markdown(f"**{headline}**")
        st.dataframe(comparison_table, hide_index=True, width="stretch")
        st.markdown(
            f"**Evidence:** {metric_help[metric_name]}. The table and chart use the same selected metric and later simulated test readings.  \n"
            "**Why it matters:** different measures answer different questions; a method that catches more injected activity may also flag ordinary readings.  \n"
            "**Context:** these are generated examples with injected labels, not F1 telemetry or observed engine failures.  \n"
            "**Next investigation:** change the data seed or test settings and check whether the comparison remains similar before drawing conclusions about this simulated example."
        )
        with st.expander("Technical Details · evaluation setup", expanded=False):
            display_metrics = result.metrics.assign(dataset_type="SYNTHETIC · illustrative sensor benchmark")
            st.dataframe(display_metrics, width="stretch", hide_index=True)
            exact_values = "; ".join(
                f"{row['model']}: {row[metric_name]:.6f}"
                for _, row in result.metrics.iterrows()
            )
            st.write(
                f"Original methods: {', '.join(result.metrics['model'].astype(str))}. "
                f"Exact selected {metric_name.replace('_', ' ')} values: {exact_values}. "
                f"Chronological split at row {result.split_index}; {result.train_normal_count} known-normal training records; "
                f"feature channels: {', '.join(features)}. Selected settings: test fraction {test_fraction:.2f}, "
                f"statistical threshold {threshold:.2f}, Isolation Forest contamination {contamination:.2f}, random state 42."
            )
    st.subheader("Held-out flag review")
    flags = result.predictions[result.predictions["baseline_flag"].eq(1) | result.predictions["isolation_forest_flag"].eq(1)]
    st.dataframe(flags.head(100), width="stretch", hide_index=True)
except (ValueError, ImportError) as exc:
    st.error(f"Could not evaluate models: {exc}")
