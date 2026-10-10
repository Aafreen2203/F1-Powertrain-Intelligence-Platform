import pandas as pd
import pytest

from src.data.fastf1_loader import FastF1DataError, list_drivers, load_driver_telemetry


def test_list_drivers_uses_available_lap_data():
    class S:
        laps = pd.DataFrame({"Driver": ["2", "1", "2", None]})
    assert list_drivers(S()) == ["1", "2"]


def test_unavailable_lap_fails_gracefully():
    class Session:
        laps = pd.DataFrame({"Driver": ["1"]})
    with pytest.raises(FastF1DataError, match="No lap found"):
        load_driver_telemetry(Session(), "9")


def test_empty_session_drivers_returns_empty_list():
    class S:
        laps = pd.DataFrame()
    assert list_drivers(S()) == []
