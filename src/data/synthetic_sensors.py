"""Reproducible illustrative sensor data; never actual F1 power-unit data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

AnomalyKind = Literal["spike", "drift", "temperature", "pressure"]


@dataclass(frozen=True)
class AnomalyEvent:
    """A generated event interval, specified by start row and duration."""

    kind: AnomalyKind
    start: int
    duration: int = 1
    magnitude: float = 1.0


DEFAULT_EVENTS = (
    AnomalyEvent("spike", start=120, duration=1, magnitude=5.0),
    AnomalyEvent("drift", start=250, duration=35, magnitude=0.08),
    AnomalyEvent("temperature", start=400, duration=25, magnitude=2.5),
    AnomalyEvent("pressure", start=550, duration=20, magnitude=2.2),
)


def generate_sensor_data(
    n_samples: int = 700,
    *,
    seed: int = 42,
    sampling_seconds: float = 1.0,
    events: tuple[AnomalyEvent, ...] | list[AnomalyEvent] | None = None,
    start: str = "2025-01-01T00:00:00Z",
) -> pd.DataFrame:
    """Generate labelled synthetic temperature, pressure, vibration and RPM.

    `anomaly_label` marks all injected event rows and `event_label` names the
    injected scenario. All generated readings are illustrative, not measured.
    """
    if n_samples < 1:
        raise ValueError("n_samples must be at least 1")
    if sampling_seconds <= 0:
        raise ValueError("sampling_seconds must be positive")
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=float) * sampling_seconds
    frame = pd.DataFrame({
        "timestamp": pd.date_range(start=start, periods=n_samples,
                                   freq=pd.to_timedelta(sampling_seconds, unit="s")),
        "temperature_c": 88 + 2.5 * np.sin(t / 90) + rng.normal(0, 0.7, n_samples),
        "pressure_kpa": 240 + 4 * np.sin(t / 65) + rng.normal(0, 1.5, n_samples),
        "vibration_mm_s": 2.2 + 0.25 * np.sin(t / 12) + rng.normal(0, 0.12, n_samples),
        "rotational_speed_rpm": 9200 + 450 * np.sin(t / 18) + rng.normal(0, 100, n_samples),
    })
    frame["anomaly_label"] = np.zeros(n_samples, dtype=np.int8)
    frame["event_label"] = "normal"
    default_events = events is None
    selected_events = DEFAULT_EVENTS if default_events else events
    for event in selected_events:
        if default_events and event.start >= n_samples:
            continue
        if default_events and event.start + event.duration > n_samples:
            event = AnomalyEvent(event.kind, event.start, n_samples - event.start, event.magnitude)
        if event.kind not in {"spike", "drift", "temperature", "pressure"}:
            raise ValueError(f"Unsupported anomaly kind: {event.kind}")
        if event.start < 0 or event.duration < 1 or event.start + event.duration > n_samples:
            raise ValueError(f"Event {event} falls outside the generated sample range")
        idx = np.arange(event.start, event.start + event.duration)
        if event.kind == "spike":
            frame.loc[idx, "vibration_mm_s"] += event.magnitude
        elif event.kind == "drift":
            frame.loc[idx, "rotational_speed_rpm"] += event.magnitude * np.arange(1, event.duration + 1) * 100
        elif event.kind == "temperature":
            frame.loc[idx, "temperature_c"] += event.magnitude
        elif event.kind == "pressure":
            frame.loc[idx, "pressure_kpa"] -= event.magnitude * 5
        frame.loc[idx, "anomaly_label"] = 1
        frame.loc[idx, "event_label"] = event.kind
    frame.attrs["dataset_type"] = "SYNTHETIC — illustrative simulated sensor readings"
    frame.attrs["seed"] = seed
    frame.attrs["source"] = "synthetic generator; not actual F1 power-unit data"
    return frame
