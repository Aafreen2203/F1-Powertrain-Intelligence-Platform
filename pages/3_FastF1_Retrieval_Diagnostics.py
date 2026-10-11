"""Temporary cross-session diagnostics for the deployed FastF1 runtime."""
import importlib.metadata
import logging
import platform
import re

import pandas as pd
import streamlit as st

from src.data.fastf1_loader import FastF1DataError, get_session_laps, load_session

DIAGNOSTIC_SESSIONS = (
    (2024, "Bahrain Grand Prix", "FP1"),
    (2024, "Bahrain Grand Prix", "FP2"),
)


def _safe_text(message: str) -> str:
    """Keep useful diagnostic text while removing queries and credentials."""
    message = re.sub(r"(https?://[^\s?#]+)\?[^\s]+", r"\1?[query omitted]", message)
    message = re.sub(r"(?i)(password|token|secret|api[_-]?key)=?[^\s,;]+", r"\1=[redacted]", message)
    message = re.sub(r"/Users/[^/\s]+", "/Users/[user]", message)
    return message


def _safe_exception_summary(exc: Exception) -> str:
    """Keep useful exception text while removing query strings and credentials."""
    return _safe_text(str(exc)) or "No exception message was provided."


class _CapturedFailureHandler(logging.Handler):
    """Capture exception summaries emitted by FastF1 and the shared loader."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.failures = []
        self.session_load_completed = False

    def emit(self, record):
        if record.getMessage().startswith("Finished loading data for "):
            self.session_load_completed = True
        if not record.exc_info:
            return
        exc = record.exc_info[1]
        if exc is None:
            return
        summary = f"{type(exc).__name__}: {_safe_exception_summary(exc)}"
        detail = f"{_safe_text(record.getMessage())} — {summary}"
        if detail not in self.failures:
            self.failures.append(detail)

st.title("FastF1 Retrieval Diagnostics")
st.warning(
    "Temporary diagnostic: this makes live public FastF1 requests for two completed sessions. "
    "It does not create or substitute synthetic telemetry."
)
st.caption(
    "Run this page in Streamlit Community Cloud to compare its runtime with local results. "
    "Underlying FastF1 request details remain in server logs; no traceback is shown here."
)

try:
    fastf1_version = importlib.metadata.version("fastf1")
except importlib.metadata.PackageNotFoundError:
    fastf1_version = "not installed"

st.write(f"**Python:** {platform.python_version()} · **FastF1:** {fastf1_version}")

if st.button("Run both session checks", type="primary"):
    results = []
    progress = st.progress(0)
    for index, (year, event, code) in enumerate(DIAGNOSTIC_SESSIONS, start=1):
        result = {
            "Selected session": f"{year} {event} · {code}",
            "FastF1 session name": "unavailable",
            "Session.load completion": "not confirmed",
            "Timing validation": "failed or unavailable",
            "Lap rows": None,
            "Timed laps": None,
            "Drivers": None,
            "Exception": None,
            "FastF1 request details": None,
        }
        failure_handler = _CapturedFailureHandler()
        fastf1_logger = logging.getLogger("fastf1")
        loader_logger = logging.getLogger("src.data.fastf1_loader")
        fastf1_logger.addHandler(failure_handler)
        loader_logger.addHandler(failure_handler)
        try:
            session = load_session(year, event, code)
            result["FastF1 session name"] = str(getattr(session, "name", "unknown"))
            laps = get_session_laps(session, load_if_needed=False)
            result.update({
                "Session.load completion": "returned",
                "Timing validation": "usable lap timing returned",
                "Lap rows": len(laps),
                "Timed laps": int(laps["LapTime"].notna().sum()) if "LapTime" in laps else 0,
                "Drivers": int(laps["Driver"].nunique(dropna=True)) if "Driver" in laps else 0,
            })
        except FastF1DataError as exc:
            result["Exception"] = f"{type(exc).__name__}: {_safe_exception_summary(exc)}"
        except Exception as exc:  # Keep diagnostics usable if an unexpected wrapper error occurs.
            result["Exception"] = f"{type(exc).__name__}: {_safe_exception_summary(exc)}"
        finally:
            fastf1_logger.removeHandler(failure_handler)
            loader_logger.removeHandler(failure_handler)
            if failure_handler.session_load_completed:
                result["Session.load completion"] = "FastF1 reported completion"
            if failure_handler.failures:
                result["FastF1 request details"] = "; ".join(failure_handler.failures)
        results.append(result)
        progress.progress(index / len(DIAGNOSTIC_SESSIONS))

    st.dataframe(pd.DataFrame(results), hide_index=True, width="stretch")
    if all(result["Timing validation"] == "usable lap timing returned" for result in results):
        st.success("Both sessions returned usable lap timing data in this runtime.")
    else:
        st.error(
            "At least one session did not return usable timing data. See the safe error summary "
            "above and the app's server logs for FastF1's underlying request details."
        )
