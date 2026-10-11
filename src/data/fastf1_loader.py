"""Access public Formula 1 session data through FastF1.

This module never fills or fabricates telemetry channels. FastF1 and network
imports are lazy so synthetic-only workflows and unit tests need no network.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
_FASTF1_LOAD_CONTEXT: ContextVar[str | None] = ContextVar("fastf1_load_context", default=None)


class _FastF1FailureHandler(logging.Handler):
    """Forward FastF1's otherwise-hidden soft-load tracebacks to app logs."""

    _TRACEBACK_PREFIX = "Traceback for failure in "
    _UNAVAILABLE_WARNINGS = {
        "Car telemetry data is unavailable!": "car telemetry",
        "Car position data is unavailable!": "car position data",
    }

    def emit(self, record: logging.LogRecord) -> None:
        load_context = _FASTF1_LOAD_CONTEXT.get()
        message = record.getMessage()
        if not load_context:
            return
        if message.startswith(self._TRACEBACK_PREFIX) and record.exc_info:
            stage = message.removeprefix(self._TRACEBACK_PREFIX)
            logger.error(
                "FastF1 partial-load failure for %s during %s",
                load_context,
                stage,
                exc_info=record.exc_info,
            )
        elif record.levelno >= logging.WARNING and message in self._UNAVAILABLE_WARNINGS:
            logger.warning(
                "FastF1 reports %s unavailable for %s; no HTTP status was retained by FastF1",
                self._UNAVAILABLE_WARNINGS[message],
                load_context,
            )


@contextmanager
def _capture_fastf1_partial_failures(load_context: str):
    """Capture detailed FastF1 soft-exception causes in server logs.

    FastF1 3.x catches most stage errors and logs their tracebacks at DEBUG,
    while its default console handler is INFO. A temporary handler retains
    those details without changing FastF1's global logging level or UI text.
    """
    try:
        import fastf1
    except ImportError:
        yield
        return
    handler = _FastF1FailureHandler(level=logging.DEBUG)
    fastf1_logger = logging.getLogger(getattr(fastf1, "__name__", "fastf1"))
    token = _FASTF1_LOAD_CONTEXT.set(load_context)
    fastf1_logger.addHandler(handler)
    try:
        yield
    finally:
        fastf1_logger.removeHandler(handler)
        _FASTF1_LOAD_CONTEXT.reset(token)


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
    try:
        path.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(path))
    except Exception as exc:
        logger.exception("Could not initialize the FastF1 cache directory")
        raise FastF1DataError(
            "FastF1 cache could not be initialized. Check server cache permissions and logs."
        ) from exc
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
        logger.exception("FastF1 event schedule retrieval failed for season=%s", season)
        raise FastF1DataError(
            f"Could not retrieve the {season} event schedule. Check server logs and retry."
        ) from exc


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
    # Keep cache setup failures distinct from API/timing retrieval failures.
    enable_cache(cache_dir)
    try:
        import fastf1
        session = fastf1.get_session(int(season), event, str(session_name))
        with _capture_fastf1_partial_failures(f"{season} {event} {session_name}"):
            session.load(telemetry=load_telemetry, laps=True, weather=True, messages=False)
            # FastF1 catches several API-stage failures and returns the Session
            # regardless. Validate actual lap timing data, not load completion
            # or the driver-result table, before exposing it to callers.
            laps = get_session_laps(session, load_if_needed=False)
        if laps.empty or not {"Driver", "LapNumber", "LapTime"}.issubset(laps.columns):
            raise FastF1DataError("FastF1 returned no usable lap timing records.")
        has_timed_lap = (
            laps["Driver"].notna() & laps["LapNumber"].notna() & laps["LapTime"].notna()
        ).any()
        if not has_timed_lap:
            raise FastF1DataError("FastF1 returned no timed lap records for this session.")
        car_data_drivers = _optional_collection_count(session, "car_data")
        position_data_drivers = _optional_collection_count(session, "pos_data")
        weather_rows = len(get_session_weather(session))
        logger.info(
            "FastF1 session validation complete for %s %s %s: lap_rows=%d "
            "lap_drivers=%d car_data_drivers=%s position_data_drivers=%s weather_rows=%d",
            season,
            event,
            session_name,
            len(laps),
            int(laps["Driver"].nunique(dropna=True)),
            car_data_drivers if car_data_drivers is not None else "unavailable",
            position_data_drivers if position_data_drivers is not None else "unavailable",
            weather_rows,
        )
        return session
    except FastF1DataError:
        logger.exception(
            "FastF1 session retrieval did not produce usable timing data for %s %s %s",
            season,
            event,
            session_name,
        )
        raise FastF1DataError(
            f"Timing data could not be retrieved for {season} {event} {session_name}. "
            "Retry or choose another session."
        ) from None
    except ValueError as exc:
        logger.exception(
            "FastF1 rejected season=%s event=%s session=%s",
            season,
            event,
            session_name,
        )
        raise FastF1DataError(
            f"FastF1 rejected {season} {event} {session_name}. "
            "Check that the session is listed for this season, then retry."
        ) from exc
    except Exception as exc:
        logger.exception(
            "FastF1 session retrieval failed for season=%s event=%s session=%s",
            season,
            event,
            session_name,
        )
        raise FastF1DataError(
            f"Could not retrieve {season} {event} {session_name}. "
            "Check the selected session and server logs, then retry."
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
            logger.exception("FastF1 lap-data retry failed")
            raise FastF1DataError(
                "Could not load session lap data; see server logs for details."
            ) from load_exc
    except AttributeError as exc:
        raise FastF1DataError("Session does not expose lap data.") from exc
    except Exception as exc:
        logger.exception("Could not access FastF1 session lap data")
        raise FastF1DataError(
            "Could not access session lap data; see server logs for details."
        ) from exc

    if laps is None:
        raise FastF1DataError("Session lap data is unavailable.")
    if not isinstance(laps, pd.DataFrame):
        raise FastF1DataError("Session lap data is not a pandas-compatible table.")
    return laps


def get_session_weather(session: Any) -> pd.DataFrame:
    """Return optional weather context, or an empty table if unavailable."""
    try:
        from fastf1.exceptions import DataNotLoadedError
    except ImportError:
        DataNotLoadedError = ()

    try:
        weather = session.weather_data
    except (DataNotLoadedError, AttributeError):
        logger.warning("FastF1 weather data is unavailable; lap context will omit weather")
        return pd.DataFrame()
    except Exception:
        logger.exception("Could not access FastF1 weather data; lap context will omit weather")
        return pd.DataFrame()
    if not isinstance(weather, pd.DataFrame):
        logger.warning("FastF1 weather data is not a DataFrame; lap context will omit weather")
        return pd.DataFrame()
    return weather


def _optional_collection_count(session: Any, attribute: str) -> int | None:
    """Count an optional FastF1 collection without treating it as required."""
    try:
        from fastf1.exceptions import DataNotLoadedError
    except ImportError:
        DataNotLoadedError = ()
    try:
        collection = getattr(session, attribute)
    except (DataNotLoadedError, AttributeError):
        return None
    except Exception:
        logger.exception("Could not inspect optional FastF1 data %s", attribute)
        return None
    try:
        return len(collection)
    except TypeError:
        return None


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
        logger.exception(
            "FastF1 telemetry extraction failed for driver=%s lap=%s",
            driver,
            lap_number if lap_number is not None else "fastest",
        )
        raise FastF1DataError(
            f"FastF1 telemetry is unavailable for driver {driver!r}; see server logs for details."
        ) from exc
    if telemetry.empty:
        raise FastF1DataError(f"Telemetry is empty for driver {driver!r}.")
    return telemetry
