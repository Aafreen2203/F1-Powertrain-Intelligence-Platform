"""Descriptive profiles and contextual lap KPIs for public telemetry."""
from __future__ import annotations

import pandas as pd


def telemetry_profile(telemetry: pd.DataFrame) -> dict[str, object]:
    """Summarize only available numeric signals and their relationships."""
    numeric = telemetry.select_dtypes(include="number").select_dtypes(
        exclude=["timedelta", "datetime"]
    )
    return {
        "record_count": len(telemetry),
        "available_columns": list(telemetry.columns),
        "signal_summary": numeric.describe().T if not numeric.empty else pd.DataFrame(),
        "correlations": numeric.corr() if numeric.shape[1] >= 2 else pd.DataFrame(),
    }


def lap_kpis(laps: pd.DataFrame, *, group_by: str = "Driver") -> pd.DataFrame:
    """Calculate descriptive best/median lap time and consistency by group.

    FastF1 lap times are timedeltas. Incomplete (missing-time) laps are
    excluded from time statistics and explicitly counted in the output.
    These comparisons do not control for track/weather/traffic conditions.
    """
    if group_by not in laps.columns:
        raise ValueError(f"Grouping column not present: {group_by}")
    if "LapTime" not in laps.columns:
        raise ValueError("LapTime column not present")
    frame = laps[[group_by, "LapTime"]].copy()
    frame["lap_time_seconds"] = pd.to_timedelta(frame["LapTime"], errors="coerce").dt.total_seconds()
    rows = []
    for key, part in frame.groupby(group_by, dropna=False):
        valid = part["lap_time_seconds"].dropna()
        rows.append({
            group_by: key,
            "completed_timed_laps": int(valid.count()),
            "incomplete_laps": int(part["lap_time_seconds"].isna().sum()),
            "best_lap_seconds": float(valid.min()) if len(valid) else float("nan"),
            "median_lap_seconds": float(valid.median()) if len(valid) else float("nan"),
            "lap_time_std_seconds": float(valid.std(ddof=1)) if len(valid) > 1 else float("nan"),
        })
    return pd.DataFrame(rows)
