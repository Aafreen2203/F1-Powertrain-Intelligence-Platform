import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.data.fastf1_loader import (
    FastF1DataError,
    enable_cache,
    list_drivers,
    load_driver_telemetry,
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
