import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastf1.exceptions import DataNotLoadedError

from src.data.fastf1_loader import (
    FastF1DataError,
    enable_cache,
    get_session_laps,
    get_session_weather,
    list_drivers,
    load_driver_telemetry,
    load_session,
)


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


def test_unavailable_optional_weather_returns_empty_table():
    class SessionWithoutWeather:
        @property
        def weather_data(self):
            raise DataNotLoadedError("Weather data was not loaded")

    assert get_session_weather(SessionWithoutWeather()).empty


class UnloadedSession:
    def __init__(self, laps=None, *, fail=False):
        self._laps = laps
        self.fail = fail
        self.load_calls = []

    @property
    def laps(self):
        if self._laps is None:
            raise DataNotLoadedError("Laps have not been loaded")
        return self._laps

    def load(self, **kwargs):
        self.load_calls.append(kwargs)
        if self.fail:
            raise RuntimeError("simulated FastF1 load failure")
        self._laps = pd.DataFrame({
            "Driver": ["2", "1", "2"],
            "LapNumber": [1, 1, 2],
            "LapTime": pd.to_timedelta([90, 91, 92], unit="s"),
        })


def test_list_drivers_loads_an_unloaded_fastf1_session_at_shared_boundary():
    session = UnloadedSession()

    assert list_drivers(session) == ["1", "2"]
    assert session.load_calls == [{"laps": True, "telemetry": False, "weather": False, "messages": False}]
    assert get_session_laps(session).equals(session.laps)


def test_load_session_verifies_laps_before_returning_and_drivers_can_be_listed(monkeypatch):
    session = UnloadedSession()
    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(get_session=lambda *_args: session))

    loaded = load_session(2024, "Example GP", "R")

    assert loaded is session
    assert session.load_calls == [{"telemetry": True, "laps": True, "weather": True, "messages": False}]
    assert list_drivers(loaded) == ["1", "2"]
    assert len(session.load_calls) == 1


def test_session_loading_failure_is_not_returned_as_success(monkeypatch):
    session = UnloadedSession(fail=True)
    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(get_session=lambda *_args: session))

    with pytest.raises(FastF1DataError, match="Could not retrieve 2024 Example GP R"):
        load_session(2024, "Example GP", "R")


def test_partial_fastf1_load_is_rejected_and_soft_failure_is_logged(monkeypatch, caplog):
    class PartialSession:
        @property
        def laps(self):
            raise DataNotLoadedError("Lap data was not loaded")

        def load(self, **_kwargs):
            try:
                raise ConnectionError("upstream returned HTTP 503")
            except ConnectionError:
                logging.getLogger("fastf1.test").debug(
                    "Traceback for failure in lap timing data", exc_info=True
                )
            logging.getLogger("fastf1.test").warning("Car telemetry data is unavailable!")

    session = PartialSession()
    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(get_session=lambda *_args: session))

    with caplog.at_level(logging.WARNING, logger="src.data.fastf1_loader"):
        with pytest.raises(FastF1DataError, match="without loaded lap data"):
            load_session(2025, "Bahrain Grand Prix", "FP1")

    assert "lap timing data" in caplog.text
    assert "upstream returned HTTP 503" in caplog.text
    assert "car telemetry unavailable for 2025 Bahrain Grand Prix FP1" in caplog.text


def test_session_without_timed_laps_is_not_a_successful_load(monkeypatch):
    class EmptyLapsSession:
        laps = pd.DataFrame({
            "Driver": ["1"],
            "LapNumber": [1],
            "LapTime": [pd.NaT],
        })

        def load(self, **_kwargs):
            pass

    session = EmptyLapsSession()
    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(get_session=lambda *_args: session))

    with pytest.raises(FastF1DataError, match="no timed lap records"):
        load_session(2025, "Bahrain Grand Prix", "FP1")


def test_invalid_fastf1_session_is_reported_as_a_retrieval_error(monkeypatch):
    def reject_session(*_args):
        raise ValueError("Unknown session identifier")

    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(get_session=reject_session))

    with pytest.raises(FastF1DataError, match="FastF1 rejected 2025 Example GP FP1"):
        load_session(2025, "Example GP", "FP1")


def test_retry_after_partial_load_creates_a_fresh_session(monkeypatch):
    partial = UnloadedSession()
    partial.load = lambda **_kwargs: None
    valid = UnloadedSession()
    sessions = iter([partial, valid])
    monkeypatch.setattr("src.data.fastf1_loader.enable_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(
        get_session=lambda *_args: next(sessions)
    ))

    with pytest.raises(FastF1DataError, match="without loaded lap data"):
        load_session(2025, "Bahrain Grand Prix", "FP1")

    assert load_session(2025, "Bahrain Grand Prix", "FP1") is valid


def test_enable_cache_defaults_to_temporary_directory(monkeypatch, tmp_path):
    enabled = []
    monkeypatch.delenv("F1_CACHE_DIR", raising=False)
    monkeypatch.setattr("src.data.fastf1_loader.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(Cache=SimpleNamespace(
        enable_cache=enabled.append
    )))

    path = enable_cache()

    assert path == Path(tmp_path) / "f1-powertrain-fastf1-cache"
    assert path.is_dir()
    assert enabled == [str(path)]


def test_enable_cache_respects_explicit_and_environment_overrides(monkeypatch, tmp_path):
    enabled = []
    monkeypatch.setitem(sys.modules, "fastf1", SimpleNamespace(Cache=SimpleNamespace(
        enable_cache=enabled.append
    )))
    env_path = tmp_path / "env-cache"
    monkeypatch.setenv("F1_CACHE_DIR", str(env_path))
    assert enable_cache() == env_path

    explicit_path = tmp_path / "explicit-cache"
    assert enable_cache(explicit_path) == explicit_path
    assert enabled == [str(env_path), str(explicit_path)]
