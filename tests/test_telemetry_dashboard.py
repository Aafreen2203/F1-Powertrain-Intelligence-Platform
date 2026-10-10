from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import src.data.fastf1_loader as fastf1_loader
from src.data.fastf1_loader import FastF1DataError

ROOT = Path(__file__).resolve().parents[1]


def telemetry_frame(n=80):
    distance = np.arange(n, dtype=float) * 10
    speed = 180 + 3 * np.sin(distance / 80)
    speed[45] = 300
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=n, freq="100ms", tz="UTC"),
        "Time": pd.to_timedelta(np.arange(n) / 10, unit="s"),
        "Distance": distance,
        "Speed": speed,
        "RPM": 9000 + 100 * np.sin(distance / 60),
        "Throttle": np.full(n, 80.0),
        "Brake": np.zeros(n, dtype=bool),
        "nGear": np.full(n, 5),
    })


class FakeSession:
    def __init__(self, laps):
        self.laps = laps


def test_explorer_load_flow_uses_existing_fastf1_loader_functions(monkeypatch):
    laps = pd.DataFrame({
        "Driver": ["1"], "LapNumber": [4], "LapTime": pd.to_timedelta([90], unit="s"),
        "IsAccurate": [True], "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
        "Sector1Time": [pd.to_timedelta([30], unit="s")],
    })
    fake = FakeSession(laps)
    monkeypatch.setattr(fastf1_loader, "list_events", lambda season: pd.DataFrame({"EventName": ["Example GP"]}))
    monkeypatch.setattr(fastf1_loader, "load_session", lambda *args: fake)
    monkeypatch.setattr(fastf1_loader, "load_driver_telemetry", lambda *args, **kwargs: telemetry_frame())
    at = AppTest.from_file(str(ROOT / "pages/1_F1_Telemetry_Explorer.py")).run()
    at.button[0].click().run()
    assert any("Loaded 1 events" in item.value for item in at.success)
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["f1_loaded_key"] == (2024, "Example GP", "FP1")
    assert at.session_state["f1_loaded_session"] is fake


def test_explorer_handles_unavailable_schedule_without_traceback(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FastF1DataError("simulated network unavailable")

    monkeypatch.setattr(fastf1_loader, "list_events", unavailable)
    at = AppTest.from_file(str(ROOT / "pages/1_F1_Telemetry_Explorer.py")).run()
    at.button[0].click().run()
    assert not at.exception
    assert any("simulated network unavailable" in error.value for error in at.error)


def test_explorer_compares_differently_sampled_laps_and_reports_retrieval_state(monkeypatch):
    laps = pd.DataFrame({
        "Driver": ["1", "1"], "LapNumber": [4, 5],
        "LapTime": pd.to_timedelta([90, 91], unit="s"),
        "IsAccurate": [True, True], "PitInTime": [pd.NaT, pd.NaT], "PitOutTime": [pd.NaT, pd.NaT],
    })
    session = FakeSession(laps)
    monkeypatch.setattr(fastf1_loader, "list_events", lambda season: pd.DataFrame({"EventName": ["Example GP"]}))
    monkeypatch.setattr(fastf1_loader, "load_session", lambda *args: session)
    monkeypatch.setattr(
        fastf1_loader,
        "load_driver_telemetry",
        lambda _session, _driver, *, lap_number=None: telemetry_frame(80 if lap_number == 4 else 63).assign(
            Speed=lambda frame: frame["Speed"] + (5 if lap_number == 5 else 0)
        ),
    )
    at = AppTest.from_file(str(ROOT / "pages/1_F1_Telemetry_Explorer.py")).run()
    at.button[0].click().run()
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["f1_retrieval_status"]["state"] == "loaded successfully"
    assert any("cache/network origin" in element.value for element in at.get("caption"))
    assert any("Engineering Interpretation" in item.value for item in at.subheader)
    assert any("Largest meaningful channel differences" in item.value for item in at.subheader)
    assert len(at.get("plotly_chart")) >= 3


def test_explorer_discloses_partial_telemetry_without_distance(monkeypatch):
    laps = pd.DataFrame({
        "Driver": ["1"], "LapNumber": [4], "LapTime": pd.to_timedelta([90], unit="s"),
        "IsAccurate": [True], "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
    })
    session = FakeSession(laps)
    monkeypatch.setattr(fastf1_loader, "list_events", lambda season: pd.DataFrame({"EventName": ["Example GP"]}))
    monkeypatch.setattr(fastf1_loader, "load_session", lambda *args: session)
    monkeypatch.setattr(fastf1_loader, "load_driver_telemetry", lambda *args, **kwargs: pd.DataFrame({"Speed": np.arange(25) + 100}))
    at = AppTest.from_file(str(ROOT / "pages/1_F1_Telemetry_Explorer.py")).run()
    at.button[0].click().run()
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["f1_retrieval_status"]["selected_lap"]["state"] == "partial/incomplete"
    assert any("no Distance channel" in item.value for item in at.warning)


def test_explorer_reports_session_retrieval_failure(monkeypatch):
    monkeypatch.setattr(fastf1_loader, "list_events", lambda season: pd.DataFrame({"EventName": ["Example GP"]}))

    def fail(*args, **kwargs):
        raise FastF1DataError("simulated session retrieval failure")

    monkeypatch.setattr(fastf1_loader, "load_session", fail)
    at = AppTest.from_file(str(ROOT / "pages/1_F1_Telemetry_Explorer.py")).run()
    at.button[0].click().run()
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["f1_retrieval_status"]["state"] == "failed"
    assert any("simulated session retrieval failure" in item.value for item in at.error)


def test_telemetry_page_consumes_loaded_session_and_exposes_exports(monkeypatch):
    laps = pd.DataFrame({
        "Driver": ["1"], "LapNumber": [4], "LapTime": pd.to_timedelta([90], unit="s"),
        "IsAccurate": [True], "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
    })
    monkeypatch.setattr(fastf1_loader, "load_driver_telemetry", lambda *args, **kwargs: telemetry_frame())
    at = AppTest.from_file(str(ROOT / "pages/2_Telemetry_Anomaly_Analysis.py")).run()
    at.session_state["f1_loaded_session"] = FakeSession(laps)
    at.session_state["f1_loaded_key"] = (2026, "Example GP", "R")
    at.run()
    assert not at.exception
    assert at.title[0].value == "Telemetry Anomaly Analysis"
    assert len(at.get("plotly_chart")) >= 2
    assert any("PUBLIC TELEMETRY" in warning.value for warning in at.warning)
    assert any("Flagged samples" in header.value for header in at.subheader)
    assert len(at.get("download_button")) == 3
    sensitivity_button = next(button for button in at.button if button.label == "Run sensitivity analysis")
    sensitivity_button.click().run()
    assert not at.exception
    assert len(at.get("dataframe")) >= 1
    assert at.session_state["real_telemetry_anomaly"]["metadata"]["lap"] == 4


def test_telemetry_page_empty_state_does_not_make_network_requests():
    at = AppTest.from_file(str(ROOT / "pages/2_Telemetry_Anomaly_Analysis.py")).run()
    assert not at.exception
    assert any("Load a public year" in item.value for item in at.info)


def test_telemetry_page_handles_session_with_no_lap_records():
    at = AppTest.from_file(str(ROOT / "pages/2_Telemetry_Anomaly_Analysis.py"))
    at.session_state["f1_loaded_session"] = FakeSession(pd.DataFrame())
    at.session_state["f1_loaded_key"] = (2026, "Example GP", "R")
    at.run()
    assert not at.exception
    assert any("no driver lap records" in warning.value for warning in at.warning)


def test_telemetry_page_reports_unsuitable_lap_without_traceback(monkeypatch):
    laps = pd.DataFrame({
        "Driver": ["1"], "LapNumber": [4], "LapTime": pd.to_timedelta([90], unit="s"),
        "IsAccurate": [True], "PitInTime": [pd.NaT], "PitOutTime": [pd.NaT],
    })
    monkeypatch.setattr(fastf1_loader, "load_driver_telemetry", lambda *args, **kwargs: pd.DataFrame({"Speed": [100]}))
    at = AppTest.from_file(str(ROOT / "pages/2_Telemetry_Anomaly_Analysis.py"))
    at.session_state["f1_loaded_session"] = FakeSession(laps)
    at.session_state["f1_loaded_key"] = (2026, "Example GP", "R")
    at.run()
    assert not at.exception
    assert any("cannot be analysed" in warning.value for warning in at.warning)


def test_synthetic_lab_remains_a_separate_labelled_page():
    at = AppTest.from_file(str(ROOT / "pages/2A_Synthetic_Sensor_Lab.py")).run()
    assert not at.exception
    assert at.title[0].value == "Synthetic Sensor Lab"
    assert any("SYNTHETIC DATA" in warning.value for warning in at.warning)


def test_engineering_reports_expose_real_and_synthetic_downloads_separately():
    from src.analytics.telemetry_anomaly import analyze_telemetry

    telemetry = telemetry_frame()
    result = analyze_telemetry(telemetry)
    at = AppTest.from_file(str(ROOT / "pages/5_Engineering_Reports.py"))
    at.session_state["real_telemetry_anomaly"] = {
        "result": result,
        "metadata": {"year": 2026, "event": "Example GP", "session": "R", "driver": "1", "lap": 4},
        "parameters": {"method": "Statistical baseline", "threshold": 6.0, "contamination": 0.03, "window": 31},
    }
    at.run()
    assert not at.exception
    assert len(at.get("download_button")) == 6
    public_labels = [button.label for button in at.get("download_button") if "public telemetry" in button.label.lower()]
    assert len(public_labels) == 3


@pytest.mark.parametrize("page", ["pages/3_Data_Quality.py", "pages/4_Model_Evaluation.py"])
def test_existing_synthetic_quality_and_evaluation_pages_still_render(page):
    at = AppTest.from_file(str(ROOT / page)).run()
    assert not at.exception
