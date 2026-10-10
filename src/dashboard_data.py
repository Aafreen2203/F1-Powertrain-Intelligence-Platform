"""Shared deterministic data helpers for Streamlit pages."""
import streamlit as st

from src.data.synthetic_sensors import generate_sensor_data


@st.cache_data(show_spinner=False)
def cached_synthetic_data(n_samples: int = 700, seed: int = 42):
    return generate_sensor_data(n_samples=n_samples, seed=seed)
