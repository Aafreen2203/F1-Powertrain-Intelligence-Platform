"""Reusable, non-destructive tabular data-quality checks."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset


def validate_frame(
    frame: pd.DataFrame,
    *,
    required_columns: list[str] | tuple[str, ...] = (),
    expected_types: dict[str, str] | None = None,
    numeric_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    timestamp_col: str | None = None,
    expected_interval: str | pd.Timedelta | None = None,
    interval_tolerance: float = 0.1,
) -> dict[str, Any]:
    """Return quality counts, warnings, failures and missing percentages.

    The function never mutates or drops records. Missing schema and invalid
    ranges are failures; missing values, duplicates and timing irregularities
    are reported as warnings for downstream review.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    rows = len(frame)
    missing_schema = [column for column in required_columns if column not in frame]
    missing_counts = frame.isna().sum().astype(int).to_dict()
    missing_percent = {key: (value / rows * 100 if rows else 0.0)
                       for key, value in missing_counts.items()}
    duplicated = int(frame.duplicated().sum())
    failures: list[str] = []
    warnings: list[str] = []
    if missing_schema:
        failures.append(f"Missing required columns: {', '.join(missing_schema)}")
    if rows == 0:
        warnings.append("Dataset contains no records")
    if duplicated:
        warnings.append(f"{duplicated} duplicate record(s)")
    missing_values = sum(missing_counts.values())
    if missing_values:
        warnings.append(f"{missing_values} missing value(s) across columns")

    type_mismatches: dict[str, dict[str, str]] = {}
    type_checks = {
        "numeric": pd.api.types.is_numeric_dtype,
        "integer": pd.api.types.is_integer_dtype,
        "datetime": pd.api.types.is_datetime64_any_dtype,
        "boolean": pd.api.types.is_bool_dtype,
    }
    for column, expected in (expected_types or {}).items():
        if column not in frame.columns:
            failures.append(f"Type check column is missing: {column}")
        elif expected not in type_checks:
            failures.append(f"Unknown expected type {expected!r} for {column}")
        elif not type_checks[expected](frame[column].dtype):
            type_mismatches[column] = {"expected": expected, "actual": str(frame[column].dtype)}
            failures.append(f"Unexpected data type for {column}: expected {expected}, got {frame[column].dtype}")

    range_violations: dict[str, int] = {}
    for column, bounds in (numeric_ranges or {}).items():
        if column not in frame.columns:
            failures.append(f"Range check column is missing: {column}")
            continue
        if not pd.api.types.is_numeric_dtype(frame[column]):
            failures.append(f"Range check column is not numeric: {column}")
            continue
        low, high = bounds
        invalid = pd.Series(False, index=frame.index)
        if low is not None:
            invalid |= frame[column] < low
        if high is not None:
            invalid |= frame[column] > high
        count = int(invalid.fillna(False).sum())
        if count:
            range_violations[column] = count
            failures.append(f"{count} out-of-range value(s) in {column}")

    ordering_violations = 0
    irregular_intervals = 0
    observed_interval_seconds: float | None = None
    if timestamp_col:
        if timestamp_col not in frame:
            failures.append(f"Timestamp column is missing: {timestamp_col}")
        else:
            timestamps = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True)
            invalid_timestamps = int(timestamps.isna().sum())
            if invalid_timestamps:
                failures.append(f"{invalid_timestamps} invalid timestamp(s) in {timestamp_col}")
            valid_times = timestamps.dropna()
            ordering_violations = int((valid_times.diff().dropna() < pd.Timedelta(0)).sum())
            if ordering_violations:
                warnings.append(f"{ordering_violations} timestamp ordering violation(s)")
            duplicate_times = int(valid_times.duplicated().sum())
            if duplicate_times:
                warnings.append(f"{duplicate_times} duplicate timestamp(s)")
            if expected_interval is not None and len(valid_times) > 1:
                deltas = valid_times.diff().dropna().dt.total_seconds()
                expected = (
                    expected_interval.total_seconds()
                    if isinstance(expected_interval, pd.Timedelta)
                    else to_offset(expected_interval).nanos / 1_000_000_000
                )
                observed_interval_seconds = float(deltas.median())
                irregular_intervals = int((np.abs(deltas - expected) > expected * interval_tolerance).sum())
                if irregular_intervals:
                    warnings.append(f"{irregular_intervals} sampling interval(s) outside tolerance")

    return {
        "record_count": rows,
        "column_count": len(frame.columns),
        "missing_counts": missing_counts,
        "missing_percent": missing_percent,
        "data_types": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "type_mismatches": type_mismatches,
        "duplicate_records": duplicated,
        "range_violations": range_violations,
        "timestamp_ordering_violations": ordering_violations,
        "irregular_intervals": irregular_intervals,
        "median_interval_seconds": observed_interval_seconds,
        "failures": failures,
        "warnings": warnings,
        "passed": not failures,
    }
