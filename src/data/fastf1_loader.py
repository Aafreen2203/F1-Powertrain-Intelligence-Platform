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
        # FastF1 can return a Session object even when lap data was not loaded
        # (for example, when the selected session/API is unsupported). Verify
        # the property before publishing the session to callers or session state.
        get_session_laps(session, load_if_needed=False)
        return session
    except Exception as exc:
        if isinstance(exc, (ValueError, FastF1DataError)):
            raise
        raise FastF1DataError(
            f"Could not load {season} {event} {session_name}: {exc}"
        ) from exc


def get_session_laps(session: Any, *, load_if_needed: bool = True) -> pd.DataFrame:
    """Return a loaded session's laps, loading them once if necessary.

    FastF1 raises ``DataNotLoadedError`` when ``Session.laps`` is accessed
    before lap loading. Callers use this shared boundary rather than accessing
    the property directly, so an unloaded session is either loaded or reported
    as a retrieval error.
    """
    try:
        from fastf1.exceptions import DataNotLoadedError
    except ImportError:
        DataNotLoadedError = ()

    try:
        laps = session.laps
    except DataNotLoadedError as exc:
        if not load_if_needed:
            raise FastF1DataError("FastF1 returned a session without loaded lap data.") from exc
        load = getattr(session, "load", None)
        if not callable(load):
            raise FastF1DataError("Session lap data is not loaded and this session cannot load it.") from exc
        try:
            load(laps=True, telemetry=False, weather=False, messages=False)
            laps = session.laps
        except Exception as load_exc:
            raise FastF1DataError(f"Could not load session lap data: {load_exc}") from load_exc
    except AttributeError as exc:
        raise FastF1DataError("Session does not expose lap data.") from exc
    except Exception as exc:
        raise FastF1DataError(f"Could not access FastF1 session lap data: {exc}") from exc

    if laps is None:
        raise FastF1DataError("Session lap data is unavailable.")
    if not isinstance(laps, pd.DataFrame):
        raise FastF1DataError("Session lap data is not a pandas-compatible table.")
    return laps


def list_drivers(session: Any) -> list[str]:
    """Return driver numbers, ensuring the session lap table is loaded first."""
    laps = get_session_laps(session)
    if laps is None or laps.empty or "Driver" not in laps.columns:
        return []
    return sorted(laps["Driver"].dropna().astype(str).unique().tolist())


def load_driver_telemetry(session: Any, driver: str, *, lap_number: int | None = None) -> pd.DataFrame:
    """Return available telemetry for a driver's fastest or selected lap.

    The returned columns are exactly those supplied by FastF1, plus any
    calculated columns FastF1 itself provides; unavailable channels stay absent.
    """
    laps = get_session_laps(session)
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
