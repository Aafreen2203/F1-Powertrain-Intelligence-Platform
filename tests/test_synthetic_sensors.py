import pandas as pd
import pytest

from src.data.synthetic_sensors import AnomalyEvent, generate_sensor_data


def test_generation_is_reproducible_and_clearly_labelled():
    first = generate_sensor_data(40, seed=7, events=[])
    second = generate_sensor_data(40, seed=7, events=[])
    pd.testing.assert_frame_equal(first, second)
    assert first.attrs["dataset_type"].startswith("SYNTHETIC")
    assert first.attrs["source"].find("not actual") >= 0
    assert first["anomaly_label"].sum() == 0
    assert set(first["event_label"]) == {"normal"}


def test_injected_events_have_known_labels_and_change_expected_signal():
    events = [AnomalyEvent("spike", 10, magnitude=6),
              AnomalyEvent("temperature", 20, duration=3, magnitude=8)]
    data = generate_sensor_data(40, seed=2, events=events)
    assert data.loc[10, "event_label"] == "spike"
    assert data.loc[10, "anomaly_label"] == 1
    assert data.loc[10, "vibration_mm_s"] > data.loc[9, "vibration_mm_s"] + 4
    assert set(data.loc[20:22, "event_label"]) == {"temperature"}
    assert data.loc[20:22, "temperature_c"].min() > data.loc[0:19, "temperature_c"].max()


@pytest.mark.parametrize("kwargs", [{"n_samples": 0}, {"n_samples": 4, "sampling_seconds": 0}])
def test_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        generate_sensor_data(**kwargs)


def test_rejects_event_outside_requested_range():
    with pytest.raises(ValueError, match="outside"):
        generate_sensor_data(10, events=[AnomalyEvent("spike", 9, duration=2)])


def test_short_default_dataset_skips_later_events_and_truncates_intersecting_events():
    data = generate_sensor_data(200)
    assert data.loc[120, "event_label"] == "spike"
    assert data["event_label"].isin(["normal", "spike"]).all()
    truncated = generate_sensor_data(270)
    assert truncated.loc[269, "event_label"] == "drift"
