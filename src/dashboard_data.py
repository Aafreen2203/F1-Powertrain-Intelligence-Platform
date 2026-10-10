"""Shared deterministic data helpers for Streamlit pages."""
import hashlib

import pandas as pd
import streamlit as st
from pandas.util import hash_pandas_object

from src.analytics.telemetry_anomaly import TelemetryAnomalyResult, analyze_telemetry
from src.data.synthetic_sensors import generate_sensor_data


@st.cache_data(show_spinner=False)
def cached_synthetic_data(n_samples: int = 700, seed: int = 42):
    return generate_sensor_data(n_samples=n_samples, seed=seed)


def _telemetry_fingerprint(telemetry: pd.DataFrame) -> str:
    """Return a stable key for the telemetry values and their alignment metadata."""
    digest = hashlib.sha256()
    schema = (telemetry.shape, tuple(telemetry.columns), tuple(map(str, telemetry.dtypes)))
    digest.update(repr(schema).encode("utf-8"))
    digest.update(hash_pandas_object(telemetry, index=True, categorize=True).values.tobytes())
    return digest.hexdigest()


@st.cache_data(show_spinner=False)
def _cached_telemetry_anomaly(
    _telemetry: pd.DataFrame,
    telemetry_fingerprint: str,
    method: str = "Statistical baseline",
    threshold: float = 6.0,
    contamination: float = 0.03,
    window: int = 31,
    random_state: int = 42,
) -> TelemetryAnomalyResult:
    """Cache analysis using a content fingerprint instead of hashing FastF1 objects."""
    # The underscore excludes the frame itself from Streamlit hashing. Its complete
    # schema, values and index are represented by telemetry_fingerprint above.
    del telemetry_fingerprint  # The value participates in Streamlit's cache key.
    return analyze_telemetry(
        _telemetry,
        method=method,
        threshold=threshold,
        contamination=contamination,
        window=window,
        random_state=random_state,
    )


def cached_telemetry_anomaly(
    telemetry,
    method: str = "Statistical baseline",
    threshold: float = 6.0,
    contamination: float = 0.03,
    window: int = 31,
    random_state: int = 42,
) -> TelemetryAnomalyResult:
    """Analyze a telemetry snapshot, caching by its contents and all controls."""
    # FastF1 Telemetry subclasses DataFrame and carries non-data metadata. Normalize
    # to a plain, private snapshot without changing the source object.
    frame = pd.DataFrame(telemetry).copy(deep=True)
    return _cached_telemetry_anomaly(
        frame,
        _telemetry_fingerprint(frame),
        method=method,
        threshold=threshold,
        contamination=contamination,
        window=window,
        random_state=random_state,
    )
