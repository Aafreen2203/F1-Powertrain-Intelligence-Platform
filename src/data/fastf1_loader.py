"""Access public Formula 1 session data through FastF1.

This module never fills or fabricates telemetry channels. FastF1 and network
imports are lazy so synthetic-only workflows and unit tests need no network.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


class FastF1DataError(RuntimeError):
    """Raised when public session data cannot be retrieved or is unavailable."""


def enable_cache(cache_dir: str | Path | None = None) -> Path:
    """Enable FastF1's disk cache and return its directory."""
    try:
        import fastf1
    except ImportError as exc:
        raise FastF1DataError("FastF1 is required for public telemetry retrieval.") from exc
    configured_cache = cache_dir or os.getenv("F1_CACHE_DIR")
    path = Path(configured_cache).expanduser() if configured_cache else (
        Path(tempfile.gettempdir()) / "f1-powertrain-fastf1-cache"
    )
    path.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(path))
    return path


def list_events(season: int, *, cache_dir: str | Path | None = None) -> pd.DataFrame:
    """Return the public event schedule for a season."""
    try:
        enable_cache(cache_dir)
        import fastf1
        schedule = fastf1.get_event_schedule(int(season), include_testing=False)
        if schedule is None or schedule.empty:
            raise FastF1DataError(f"No event schedule is available for {season}.")
        return schedule.copy()
    except FastF1DataError:
        raise
    except Exception as exc:
        raise FastF1DataError(f"Could not retrieve the {season} event schedule: {exc}") from exc


def load_session(
    season: int,
    event: str | int,
    session_name: str,
    *,
    cache_dir: str | Path | None = None,
    load_telemetry: bool = True,
) -> Any:
    """Load and return a FastF1 Session; telemetry loading is optional."""
    if not session_name or not str(session_name).strip():
        raise ValueError("session_name must be supplied (for example 'Q' or 'R').")
    try:
        enable_cache(cache_dir)
        import fastf1
        session = fastf1.get_session(int(season), event, str(session_name))
        session.load(telemetry=load_telemetry, laps=True, weather=True, messages=False)
        return session
    except Exception as exc:
        if isinstance(exc, (ValueError, FastF1DataError)):
            raise
        raise FastF1DataError(
            f"Could not load {season} {event} {session_name}: {exc}"
        ) from exc


def list_drivers(session: Any) -> list[str]:
    """Return driver numbers present in a loaded session's lap table."""
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty or "Driver" not in laps.columns:
        return []
    return sorted(laps["Driver"].dropna().astype(str).unique().tolist())


def load_driver_telemetry(session: Any, driver: str, *, lap_number: int | None = None) -> pd.DataFrame:
    """Return available telemetry for a driver's fastest or selected lap.

    The returned columns are exactly those supplied by FastF1, plus any
    calculated columns FastF1 itself provides; unavailable channels stay absent.
    """
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty:
        raise FastF1DataError("Session has no lap data available.")
    if "Driver" not in laps.columns:
        raise FastF1DataError("Session lap data has no Driver column.")
    selected = laps[laps["Driver"].astype(str) == str(driver)]
    if lap_number is not None:
        if "LapNumber" not in selected.columns:
            raise FastF1DataError("Session lap data has no LapNumber column.")
        selected = selected[selected["LapNumber"] == lap_number]
    if selected.empty:
        raise FastF1DataError(f"No lap found for driver {driver!r}.")
    if lap_number is None and "LapTime" in selected.columns:
        selected = selected.dropna(subset=["LapTime"]).sort_values("LapTime").head(1)
    if selected.empty:
        raise FastF1DataError(f"No timed lap found for driver {driver!r}.")
    try:
        telemetry = selected.iloc[0].get_telemetry().copy()
    except Exception as exc:
        raise FastF1DataError(f"Telemetry is unavailable for driver {driver!r}: {exc}") from exc
    if telemetry.empty:
        raise FastF1DataError(f"Telemetry is empty for driver {driver!r}.")
    return telemetry
