"""Distance-aligned descriptive comparison of public FastF1 lap telemetry."""
from __future__ import annotations

import numpy as np
import pandas as pd


class LapComparisonError(ValueError):
    """Raised when two laps do not contain comparable distance-based signals."""


SIGNALS = ("Speed", "RPM", "Throttle", "Brake", "nGear")
CONTEXT_COLUMNS = (
    "LapNumber", "LapTime", "IsAccurate", "Deleted", "DeletedReason",
    "PitInTime", "PitOutTime", "Stint", "Compound", "TyreLife", "TrackStatus",
)
VALIDITY_COLUMNS = ("LapTime", "IsAccurate", "Deleted", "PitInTime", "PitOutTime")


def unavailable_lap_markers(laps: pd.DataFrame) -> list[str]:
    """List FastF1 validity fields absent from this session's lap schema."""
    return [column for column in VALIDITY_COLUMNS if column not in laps.columns]


def _has_value(value: object) -> bool:
    missing = pd.isna(value)
    return not bool(missing) if isinstance(missing, (bool, np.bool_)) else True


def _is_marked(value: object) -> bool:
    if not _has_value(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def classify_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Classify lap rows using only explicit timing, validity, deletion and pit markers.

    Missing optional metadata does not itself exclude a lap. The returned copy
    retains the provider rows and adds reasoned eligibility fields.
    """
    if not isinstance(laps, pd.DataFrame):
        raise TypeError("laps must be a pandas DataFrame")
    result = laps.copy(deep=True)
    eligible = []
    reasons_by_row = []
    for _, row in result.iterrows():
        reasons = []
        if "LapNumber" not in result or not _has_value(row.get("LapNumber")):
            reasons.append("lap number unavailable")
        if "LapTime" not in result or not _has_value(row.get("LapTime")):
            reasons.append("timed lap unavailable (incomplete or unrecorded)")
        if "IsAccurate" in result and _has_value(row.get("IsAccurate")) and not _is_marked(row["IsAccurate"]):
            reasons.append("FastF1 marks lap as inaccurate")
        if "Deleted" in result and _is_marked(row.get("Deleted")):
            reason = row.get("DeletedReason")
            suffix = f": {reason}" if _has_value(reason) else ""
            reasons.append(f"FastF1 marks lap as deleted{suffix}")
        for column, label in (("PitInTime", "pit-in"), ("PitOutTime", "pit-out")):
            if column in result and _has_value(row.get(column)):
                reasons.append(f"lap has {label} marker")
        reasons_by_row.append("; ".join(reasons))
        eligible.append(not reasons)
    result["comparison_eligible"] = eligible
    result["exclusion_reasons"] = reasons_by_row
    return result


def lap_weather_at_midpoint(weather: pd.DataFrame, lap: pd.Series) -> pd.Series | None:
    """Return the nearest available session-weather sample to a lap midpoint."""
    if not isinstance(weather, pd.DataFrame) or weather.empty or "Time" not in weather:
        return None
    start = pd.to_timedelta(lap.get("LapStartTime"), errors="coerce")
    duration = pd.to_timedelta(lap.get("LapTime"), errors="coerce")
    if pd.isna(start) or pd.isna(duration):
        return None
    sample_times = pd.to_timedelta(weather["Time"], errors="coerce")
    valid = sample_times.notna()
    if not valid.any():
        return None
    target = start + duration / 2
    valid_positions = np.flatnonzero(valid.to_numpy())
    offsets = (sample_times.iloc[valid_positions] - target).abs()
    nearest_index = int(np.argmin(offsets.to_numpy()))
    selected_position = int(valid_positions[nearest_index])
    selected = weather.iloc[selected_position].copy()
    selected["lap_midpoint_offset_seconds"] = float(offsets.iloc[nearest_index].total_seconds())
    return selected


def _interpolate_continuous(source: pd.DataFrame, channel: str, grid: np.ndarray) -> np.ndarray:
    """Interpolate only within adjacent finite source pairs; do not bridge gaps."""
    x = source["Distance"].to_numpy(dtype=float)
    values = pd.to_numeric(source[channel], errors="coerce").to_numpy(dtype=float)
    result = np.full(len(grid), np.nan)
    for index in range(len(x) - 1):
        if not (np.isfinite(values[index]) and np.isfinite(values[index + 1])):
            continue
        mask = (grid >= x[index]) & (grid <= x[index + 1])
        result[mask] = np.interp(grid[mask], x[index:index + 2], values[index:index + 2])
    return result


def _clean_lap(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise LapComparisonError(f"{label} lap has no telemetry samples.")
    if "Distance" not in frame:
        raise LapComparisonError(f"{label} lap has no Distance channel.")
    result = pd.DataFrame(frame).copy(deep=True)
    result["Distance"] = pd.to_numeric(result["Distance"], errors="coerce")
    result = result[np.isfinite(result["Distance"])].sort_values("Distance", kind="stable")
    result = result.drop_duplicates("Distance", keep="last")
    if len(result) < 2:
        raise LapComparisonError(f"{label} lap needs at least two unique distance samples.")
    return result


def align_laps_by_distance(
    reference: pd.DataFrame,
    comparison: pd.DataFrame,
    *,
    step_m: float = 5.0,
) -> pd.DataFrame:
    """Interpolate numeric channels on a shared distance grid over lap overlap.

    The returned raw source frames are not modified. The comparison convention
    is always comparison minus reference, so positive speed delta means the
    comparison lap was faster at that distance. Categorical/boolean gear and
    brake values use nearest source sample; continuous channels use linear
    interpolation. Interpolation smooths short transients and is descriptive.
    """
    if not np.isfinite(step_m) or step_m <= 0:
        raise ValueError("step_m must be positive and finite")
    ref = _clean_lap(reference, "Reference")
    comp = _clean_lap(comparison, "Comparison")
    low = max(float(ref["Distance"].min()), float(comp["Distance"].min()))
    high = min(float(ref["Distance"].max()), float(comp["Distance"].max()))
    if high <= low:
        raise LapComparisonError("The laps have no overlapping distance range.")
    grid = np.arange(low, high, step_m, dtype=float)
    if len(grid) == 0 or grid[-1] < high:
        grid = np.append(grid, high)
    aligned = pd.DataFrame({"Distance": grid})
    for prefix, source in (("reference", ref), ("comparison", comp)):
        if "Time" in source:
            seconds = pd.to_timedelta(source["Time"], errors="coerce").dt.total_seconds()
            aligned[f"{prefix}_time_s"] = _interpolate_continuous(
                source.assign(_time_seconds=seconds), "_time_seconds", grid
            )
    common = [channel for channel in SIGNALS if channel in ref and channel in comp]
    for channel in SIGNALS:
        if channel not in ref and channel not in comp:
            continue
        for prefix, source in (("reference", ref), ("comparison", comp)):
            if channel not in source:
                continue
            if channel in {"Brake", "nGear"}:
                # Nearest-neighbour context avoids inventing fractional states.
                x = source["Distance"].to_numpy(dtype=float)
                idx = np.searchsorted(x, grid).clip(0, len(x) - 1)
                previous = np.maximum(idx - 1, 0)
                idx = np.where(np.abs(x[previous] - grid) <= np.abs(x[idx] - grid), previous, idx)
                aligned[f"{prefix}_{channel}"] = source[channel].iloc[idx].to_numpy()
            else:
                aligned[f"{prefix}_{channel}"] = _interpolate_continuous(source, channel, grid)
        if channel in common and channel not in {"Brake", "nGear"}:
            aligned[f"delta_{channel}"] = aligned[f"comparison_{channel}"] - aligned[f"reference_{channel}"]
    if not common:
        raise LapComparisonError("The laps have no shared comparison channels.")
    return aligned


def lap_difference_summary(aligned: pd.DataFrame) -> pd.DataFrame:
    """Summarize largest absolute differences and retain alignment coverage."""
    rows = []
    for channel in ("Speed", "RPM", "Throttle"):
        delta_col = f"delta_{channel}"
        if delta_col not in aligned or aligned[delta_col].notna().sum() == 0:
            continue
        index = aligned[delta_col].abs().idxmax()
        compared = aligned[delta_col].notna()
        valid_count = int(compared.sum())
        rows.append({
            "channel": channel,
            "distance_m": float(aligned.loc[index, "Distance"]),
            "reference_value": float(aligned.loc[index, f"reference_{channel}"]),
            "comparison_value": float(aligned.loc[index, f"comparison_{channel}"]),
            "delta_comparison_minus_reference": float(aligned.loc[index, delta_col]),
            "mean_absolute_difference": float(aligned.loc[compared, delta_col].abs().mean()),
            "valid_aligned_samples": valid_count,
            "aligned_grid_samples": len(aligned),
            "coverage_fraction": valid_count / len(aligned) if len(aligned) else 0.0,
            "reference_time_s": float(aligned.loc[index, "reference_time_s"]) if "reference_time_s" in aligned else np.nan,
            "comparison_time_s": float(aligned.loc[index, "comparison_time_s"]) if "comparison_time_s" in aligned else np.nan,
        })
    return pd.DataFrame(rows)
