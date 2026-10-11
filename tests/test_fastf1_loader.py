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
        self._laps = pd.DataFrame({"Driver": ["2", "1", "2"]})


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

    with pytest.raises(FastF1DataError, match="Could not load 2024 Example GP R: simulated FastF1 load failure"):
        load_session(2024, "Example GP", "R")


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
