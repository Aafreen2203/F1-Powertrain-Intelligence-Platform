import pandas as pd
import pytest

from src.data.synthetic_sensors import AnomalyEvent, generate_sensor_data
from src.models.anomaly import evaluate_anomaly_methods, statistical_baseline

FEATURES = ["temperature_c", "pressure_kpa", "vibration_mm_s", "rotational_speed_rpm"]


def test_statistical_baseline_flags_extreme_row_and_explains_signal():
    train = pd.DataFrame({"x": [0.0, 0.1, -0.1, 0.05, -0.05]})
    flags, reasons = statistical_baseline(train, pd.DataFrame({"x": [0.0, 20.0]}), threshold=3)
    assert flags.tolist() == [0, 1]
    assert "robust-z" in reasons.iloc[1, 0]


def test_models_evaluate_only_chronologically_later_data_and_exclude_labels():
    data = generate_sensor_data(600, seed=11, events=[
        AnomalyEvent("temperature", start=500, duration=30, magnitude=7),
        AnomalyEvent("spike", start=540, duration=1, magnitude=8),
    ])
    result = evaluate_anomaly_methods(data, feature_cols=FEATURES, test_fraction=0.25,
                                     contamination=0.04, random_state=3)
    assert result.split_index == 450
    assert result.train_normal_count == 450
    assert len(result.predictions) == 150
    assert "anomaly_label" not in result.predictions.columns
    assert result.predictions["ground_truth"].sum() == 31
    assert set(result.metrics["model"]) == {"Statistical robust-z baseline", "Isolation Forest"}
    assert result.metrics[["precision", "recall", "f1", "false_positive_rate"]].notna().all().all()
    assert result.metrics[["precision", "recall", "f1", "false_positive_rate"]].apply(
        lambda col: col.between(0, 1).all()).all()
    assert result.predictions.loc[result.predictions["ground_truth"].eq(1), "baseline_reason"].str.len().gt(0).all()


def test_rejects_label_leakage_and_missing_features():
    data = generate_sensor_data(30, events=[])
    with pytest.raises(ValueError, match="must not"):
        evaluate_anomaly_methods(data, feature_cols=FEATURES + ["anomaly_label"])
    with pytest.raises(ValueError, match="not present"):
        evaluate_anomaly_methods(data, feature_cols=["imaginary"])


def test_rejects_unsorted_or_invalid_timestamp_order():
    data = generate_sensor_data(50, events=[])
    data = data.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="sorted by timestamp"):
        evaluate_anomaly_methods(data, feature_cols=FEATURES)


def test_rejects_non_binary_fractional_labels_instead_of_coercing_them():
    data = generate_sensor_data(50, events=[])
    data["anomaly_label"] = data["anomaly_label"].astype(float)
    data.loc[0, "anomaly_label"] = 0.5
    with pytest.raises(ValueError, match="binary"):
        evaluate_anomaly_methods(data, feature_cols=FEATURES)
