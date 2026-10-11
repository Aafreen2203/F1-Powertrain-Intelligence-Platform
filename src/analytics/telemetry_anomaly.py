"""Unlabelled, contextual anomaly screening for one real FastF1 lap.

Scores identify telemetry that merits inspection. They are not fault labels or
out-of-sample performance estimates. No synthetic values are created here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.validation.quality import validate_frame

CORE_CHANNELS = ("Speed", "RPM", "Throttle", "Brake", "nGear")
MIN_SAMPLES = 20
MINIMUM_SIGNAL_SCALES = {"Speed": 1.0, "RPM": 50.0, "Throttle": 10.0, "nGear": 0.5}
CHANNEL_UNITS = {
    "Speed": "km/h",
    "RPM": "rpm",
    "Throttle": "%",
    "Brake": "boolean applied/not applied",
    "nGear": "gear number",
}


def _feature_description(feature: str) -> tuple[str, str, str, str]:
    """Return raw channel, raw unit, feature unit, and exact feature definition."""
    channel = feature.removesuffix("_change")
    raw_unit = CHANNEL_UNITS.get(channel, "provider units")
    if feature.endswith("_change"):
        feature_unit = {
            "Speed": "km/h per provider sample",
            "RPM": "rpm per provider sample",
            "Throttle": "percentage points per provider sample",
        }.get(channel, f"{raw_unit} per provider sample")
        definition = f"current {channel} minus immediately preceding cleaned row after distance sorting; missing values are not bridged"
    else:
        feature_unit = raw_unit
        definition = f"current raw {channel} sample"
    return channel, raw_unit, feature_unit, definition


class TelemetryAnalysisError(ValueError):
    """Raised when a lap cannot support telemetry anomaly analysis."""


@dataclass
class TelemetryAnomalyResult:
    """Scored samples plus quality diagnostics for a selected lap."""

    samples: pd.DataFrame
    quality: dict[str, object]
    available_channels: list[str]
    method: str
    threshold: float
    contamination: float


def _numeric_signal(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]
    if column == "Brake" and pd.api.types.is_bool_dtype(values):
        return values.astype(float)
    return pd.to_numeric(values, errors="coerce").astype(float)


def _prepare_samples(telemetry: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    if not isinstance(telemetry, pd.DataFrame) or telemetry.empty:
        raise TelemetryAnalysisError("No telemetry samples are available for this lap.")
    if "Distance" not in telemetry:
        raise TelemetryAnalysisError("This lap has no Distance channel, which is required for analysis.")

    original = telemetry.copy()
    distance = pd.to_numeric(original["Distance"], errors="coerce")
    invalid_distance = int((~np.isfinite(distance)).sum())
    ordered = original.assign(_distance=distance).loc[np.isfinite(distance)].copy()
    order_violations = int((ordered["_distance"].diff().dropna() < 0).sum())
    duplicates = int(ordered["_distance"].duplicated(keep="last").sum())
    # Duplicate distance samples are retained once, deterministically keeping
    # the last provider sample after stable sorting; timestamps stay attached.
    ordered = ordered.sort_values("_distance", kind="stable")
    ordered = ordered.drop_duplicates("_distance", keep="last").copy()
    ordered["Distance"] = ordered.pop("_distance")
    channels = [name for name in CORE_CHANNELS if name in ordered.columns]
    if not channels:
        raise TelemetryAnalysisError("None of Speed, RPM, Throttle, Brake, or nGear is available.")

    signals = pd.DataFrame(index=ordered.index)
    nonfinite: dict[str, int] = {}
    channel_availability = {channel: "not provided" for channel in CORE_CHANNELS}
    for channel in channels:
        values = _numeric_signal(ordered, channel)
        nonfinite[channel] = int(np.isinf(values).sum())
        # Nonfinite provider readings are treated as missing for downstream
        # scoring/plotting and counted explicitly; no value is imputed.
        if nonfinite[channel]:
            ordered[channel] = values.replace([np.inf, -np.inf], np.nan)
        signals[channel] = values.replace([np.inf, -np.inf], np.nan)
        finite_values = signals[channel].dropna()
        if channel in {"Brake", "nGear"} and len(finite_values) >= 1:
            channel_availability[channel] = "available as context; not directly scored"
        elif len(finite_values) < 2:
            channel_availability[channel] = "fewer than two finite readings"
        elif finite_values.nunique() <= 1:
            channel_availability[channel] = "constant on selected lap"
        else:
            channel_availability[channel] = "available for analysis"
    channels = [c for c in channels if signals[c].notna().sum() >= 2 and signals[c].nunique(dropna=True) > 1]
    if not channels:
        raise TelemetryAnalysisError("Available telemetry channels are missing or constant on this lap.")
    scored_channels = [channel for channel in channels if channel not in {"Brake", "nGear"}]
    if not scored_channels:
        raise TelemetryAnalysisError("No varying Speed, RPM, or Throttle channel is available to score.")
    has_signal = signals[channels].notna().any(axis=1)
    no_signal_samples = int((~has_signal).sum())
    ordered = ordered.loc[has_signal].copy()
    signals = signals.loc[ordered.index, channels]
    if len(ordered) < MIN_SAMPLES:
        raise TelemetryAnalysisError(
            f"Only {len(ordered)} usable samples remain; at least {MIN_SAMPLES} are required."
        )

    time_column = "Date" if "Date" in ordered else None
    quality = validate_frame(ordered, timestamp_col=time_column)
    quality.update({
        "source_ordering_violations": order_violations,
        "duplicate_distance_samples_removed": duplicates,
        "invalid_distance_samples_removed": invalid_distance,
        "nonfinite_channel_values": nonfinite,
        "channel_availability": channel_availability,
        "samples_without_usable_channels_removed": no_signal_samples,
        "analysis_channels": scored_channels,
        "context_channels": [channel for channel in channels if channel in {"Brake", "nGear"}],
        "distance_monotonic_after_cleanup": bool(ordered["Distance"].is_monotonic_increasing),
        "distance_duplicate_count_after_cleanup": int(ordered["Distance"].duplicated().sum()),
        "rows_used": len(ordered),
    })
    if "Throttle" in ordered:
        throttle = _numeric_signal(ordered, "Throttle")
        outside_documented_range = int(((throttle < 0) | (throttle > 100)).sum())
        quality["throttle_outside_documented_0_100_percent_count"] = outside_documented_range
        if outside_documented_range:
            quality["warnings"] = [
                *quality.get("warnings", []),
                f"{outside_documented_range} Throttle samples are outside FastF1's documented 0–100% range; they were retained as provided and should be checked against pit/track status.",
            ]
    # Returned signal values are coerced only in the private analysis frame;
    # source values remain in the sample table and are never imputed.
    for channel in channels:
        ordered[f"_signal_{channel}"] = signals[channel]
    return ordered.reset_index(drop=True), quality, channels


def _context_features(
    samples: pd.DataFrame, channels: list[str], window: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    score_channels = [channel for channel in channels if channel not in {"Brake", "nGear"}]
    context_signals = [channel for channel in channels if channel != "Brake"]
    context = pd.DataFrame({c: samples[f"_signal_{c}"] for c in context_signals})
    signals = context[score_channels]
    features = signals.copy()
    for channel in score_channels:
        if channel in {"Speed", "RPM", "Throttle"}:
            features[f"{channel}_change"] = signals[channel].diff()
    contextual = features.copy()
    gear_changed = pd.Series(False, index=samples.index)
    if "nGear" in context:
        gear_changed = context["nGear"].ne(context["nGear"].shift())
    shift_context = gear_changed | gear_changed.shift(fill_value=False)
    brake_context = pd.Series(False, index=samples.index)
    if "Brake" in channels:
        brake_values = _numeric_signal(samples, "Brake").fillna(0.0)
        brake_active = brake_values.gt(0.5)
        brake_context = brake_active | brake_active.shift(fill_value=False)
    if "RPM_change" in contextual:
        # Shift transients and adjacent braking samples are driving context,
        # not standalone evidence of an RPM-change anomaly.
        rpm_context = shift_context | brake_context
        contextual.loc[rpm_context, "RPM_change"] = np.nan
    if "Speed_change" in contextual:
        contextual.loc[brake_context, "Speed_change"] = np.nan
    if "Throttle_change" in contextual:
        contextual.loc[brake_context, "Throttle_change"] = np.nan
    for channel in ("Speed", "Throttle"):
        if channel in contextual:
            contextual.loc[brake_context, channel] = np.nan
    for channel in ("nGear", "RPM"):
        if channel in contextual:
            contextual.loc[shift_context, channel] = np.nan

    scores = pd.DataFrame(index=contextual.index)
    baselines = pd.DataFrame(index=contextual.index)
    min_periods = min(5, max(2, window // 4))
    for column in contextual:
        values = contextual[column].replace([np.inf, -np.inf], np.nan)
        past = values.shift(1)
        center = past.rolling(window=window, min_periods=min_periods).median()
        baselines[column] = center
        mad = past.rolling(window=window, min_periods=min_periods).apply(
            lambda array: float(np.median(np.abs(array - np.median(array)))), raw=True
        )
        scale = 1.4826 * mad
        if column.endswith("_change"):
            source_channel = column.removesuffix("_change")
            channel_level = signals[source_channel].shift(1)
            scale_reference = channel_level.rolling(window=window, min_periods=min_periods).median()
        else:
            source_channel = column
            scale_reference = center
        floor = scale_reference.abs().mul(0.01).clip(
            lower=MINIMUM_SIGNAL_SCALES.get(source_channel, 1e-3)
        )
        # Quantized/flat windows often have zero MAD. Fall back to causal
        # preceding-window standard deviation, then to 1% of the local level
        # (with an absolute floor) rather than exploding the score denominator.
        fallback = past.rolling(window=window, min_periods=min_periods).std(ddof=0)
        scale = scale.where(scale > floor, fallback)
        scale = scale.where(scale > floor, floor)
        scores[column] = (values - center).abs().div(scale)
    return features, scores.replace([np.inf, -np.inf], np.nan), baselines


def analyze_telemetry(
    telemetry: pd.DataFrame,
    *,
    method: str = "Statistical baseline",
    threshold: float = 6.0,
    contamination: float = 0.03,
    window: int = 31,
    random_state: int = 42,
) -> TelemetryAnomalyResult:
    """Score one lap using causal robust deviations or exploratory Isolation Forest."""
    if method not in {"Statistical baseline", "Isolation Forest"}:
        raise ValueError("method must be Statistical baseline or Isolation Forest")
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be in (0, 0.5]")
    if window < 3:
        raise ValueError("window must be at least 3")

    samples, quality, channels = _prepare_samples(telemetry)
    features, contextual_scores, local_baselines = _context_features(samples, channels, window)
    max_score = contextual_scores.max(axis=1, skipna=True)
    top_feature = contextual_scores.fillna(-np.inf).idxmax(axis=1)
    top_feature = top_feature.where(contextual_scores.notna().any(axis=1), "")

    if method == "Statistical baseline":
        scores = max_score.astype(float)
        flags = scores.ge(threshold) & max_score.notna()
        effective_threshold = threshold
    else:
        # The forest is deliberately fit and scored on this same unlabelled lap.
        # This is exploratory single-lap outlier screening, not a holdout metric.
        model_features = features.replace([np.inf, -np.inf], np.nan)
        usable = model_features.notna().all(axis=1)
        if int(usable.sum()) < MIN_SAMPLES:
            raise TelemetryAnalysisError(
                f"Isolation Forest needs {MIN_SAMPLES} complete feature rows; "
                f"only {int(usable.sum())} are available."
            )
        forest = IsolationForest(contamination=contamination, random_state=random_state)
        forest.fit(model_features.loc[usable])
        forest_scores = -forest.decision_function(model_features.loc[usable])
        scores = pd.Series(np.nan, index=samples.index, dtype=float)
        scores.loc[usable] = forest_scores
        flags = pd.Series(False, index=samples.index)
        flags.loc[usable] = forest.predict(model_features.loc[usable]) == -1
        effective_threshold = float("nan")

    samples["anomaly_score"] = scores.to_numpy()
    samples["is_potential_anomaly"] = flags.to_numpy(dtype=bool)
    samples["feature_or_channel"] = top_feature.to_numpy()
    selected_observed = np.full(len(samples), np.nan)
    selected_reference = np.full(len(samples), np.nan)
    selected_context_score = np.full(len(samples), np.nan)
    for feature in contextual_scores.columns:
        selected = top_feature.eq(feature).to_numpy()
        selected_observed[selected] = features[feature].to_numpy()[selected]
        selected_reference[selected] = local_baselines[feature].to_numpy()[selected]
        selected_context_score[selected] = contextual_scores[feature].to_numpy()[selected]
    samples["observed_feature_value"] = selected_observed
    samples["local_reference_value"] = selected_reference
    samples["contextual_feature_score"] = selected_context_score
    descriptions = {
        feature: _feature_description(feature) for feature in contextual_scores.columns
    }
    samples["raw_channel"] = samples["feature_or_channel"].map(
        lambda feature: descriptions.get(feature, ("", "", "", ""))[0]
    )
    samples["raw_channel_unit"] = samples["raw_channel"].map(CHANNEL_UNITS)
    samples["raw_channel_value"] = [
        pd.to_numeric(samples[channel], errors="coerce").iloc[index]
        if channel in samples else np.nan
        for index, channel in enumerate(samples["raw_channel"])
    ]
    samples["feature_unit"] = samples["feature_or_channel"].map(
        lambda feature: descriptions.get(feature, ("", "", "", ""))[2]
    )
    samples["feature_definition"] = samples["feature_or_channel"].map(
        lambda feature: descriptions.get(feature, ("", "", "", ""))[3]
    )
    samples["configured_threshold"] = effective_threshold
    samples["configured_contamination"] = contamination
    if method == "Statistical baseline":
        flagged_explanations = []
        for index, feature in enumerate(top_feature):
            if not feature or not np.isfinite(selected_observed[index]) or not np.isfinite(selected_reference[index]):
                flagged_explanations.append("No contextual feature score or preceding reference was available.")
                continue
            unit = descriptions[feature][2]
            flagged_explanations.append(
                f"{feature} value = {selected_observed[index]:.2f} {unit}; preceding-window median "
                f"= {selected_reference[index]:.2f} {unit}; absolute robust deviation "
                f"= {selected_context_score[index]:.2f} scale units, above threshold "
                f"{threshold:.2f}. This is a statistical flag, not a causal diagnosis."
            )
    else:
        flagged_explanations = []
        for index, feature in enumerate(top_feature):
            detail = (
                f"{feature} value = {selected_observed[index]:.2f} {descriptions[feature][2]}; "
                f"preceding-window median = {selected_reference[index]:.2f} "
                f"{descriptions[feature][2]}; contextual deviation = "
                f"{selected_context_score[index]:.2f} scale units. "
                if feature and np.isfinite(selected_observed[index]) and np.isfinite(selected_reference[index])
                else ""
            )
            flagged_explanations.append(
                f"Isolation Forest marked this row as an in-sample multichannel outlier "
                f"(negative decision function {scores.iloc[index]:.4f}, unitless; contamination "
                f"{contamination:.2f}). {detail}This is exploratory and not a causal diagnosis."
            )
    samples["explanation"] = np.where(flags, flagged_explanations, "No score exceeded the selected rule.")
    samples["anomaly_score_definition"] = (
        "negative Isolation Forest decision function; unitless"
        if method == "Isolation Forest"
        else "maximum absolute contextual residual divided by robust local scale; unitless"
    )
    samples["segment_id"] = pd.Series(pd.NA, index=samples.index, dtype="Int64")
    # A segment is a contiguous run in sample order; single clean samples split runs.
    starts = flags & ~flags.shift(fill_value=False)
    segment_numbers = starts.cumsum()
    samples.loc[flags, "segment_id"] = segment_numbers[flags].astype(int)
    samples = samples.drop(columns=[c for c in samples if c.startswith("_signal_")])
    quality.update({
        "potential_anomaly_sample_count": int(flags.sum()),
        "potential_anomaly_segment_count": int(samples.loc[flags, "segment_id"].nunique()),
        "unscored_samples": int(scores.isna().sum()),
        "method_note": (
            "Causal robust deviation against preceding samples; no labels or future samples used."
            if method == "Statistical baseline" else
            "Unsupervised Isolation Forest fit and scored on this same unlabelled lap; exploratory, not out-of-sample."
        ),
    })
    return TelemetryAnomalyResult(samples, quality, channels, method, effective_threshold, contamination)


def summarize_anomaly_segments(samples: pd.DataFrame) -> pd.DataFrame:
    """Summarize contiguous flagged sample runs without joining across clean samples."""
    flagged = samples.loc[samples["is_potential_anomaly"]].copy()
    columns = ["segment_id", "sample_count", "distance_start_m", "distance_end_m",
               "time_start", "time_end", "top_feature", "observed_min", "observed_max",
               "feature_unit", "feature_definition", "raw_channel", "raw_channel_unit",
               "raw_channel_value_min", "raw_channel_value_max", "local_reference_median",
               "configured_threshold", "configured_contamination", "brake_context",
               "gear_context", "max_score", "explanation"]
    if flagged.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for segment_id, part in flagged.groupby("segment_id", dropna=True, sort=True):
        top = part["feature_or_channel"].mode()
        feature = str(top.iloc[0]) if not top.empty else ""
        feature_rows = part[part["feature_or_channel"] == feature] if feature else part.iloc[0:0]
        explanation_rows = feature_rows if not feature_rows.empty else part
        explanation = explanation_rows.loc[explanation_rows["anomaly_score"].idxmax(), "explanation"]
        if "observed_feature_value" in feature_rows:
            observed = pd.to_numeric(feature_rows["observed_feature_value"], errors="coerce").dropna()
        else:
            channel = feature.removesuffix("_change")
            observed = pd.to_numeric(feature_rows[channel], errors="coerce").dropna() if channel in feature_rows else pd.Series(dtype=float)
        reference_values = (
            pd.to_numeric(feature_rows["local_reference_value"], errors="coerce").dropna()
            if "local_reference_value" in feature_rows else pd.Series(dtype=float)
        )
        raw_values = (
            pd.to_numeric(feature_rows["raw_channel_value"], errors="coerce").dropna()
            if "raw_channel_value" in feature_rows else pd.Series(dtype=float)
        )
        brake_context = (
            "brake active" if "Brake" in part and _numeric_signal(part, "Brake").fillna(0).gt(0.5).any()
            else "brake inactive or unavailable"
        )
        gears = part["nGear"].dropna().unique().tolist() if "nGear" in part else []
        row = {
            "segment_id": int(segment_id),
            "sample_count": len(part),
            "distance_start_m": float(part["Distance"].min()),
            "distance_end_m": float(part["Distance"].max()),
            "time_start": part["Date"].min() if "Date" in part else (part["Time"].min() if "Time" in part else pd.NaT),
            "time_end": part["Date"].max() if "Date" in part else (part["Time"].max() if "Time" in part else pd.NaT),
            "top_feature": feature,
            "observed_min": float(observed.min()) if len(observed) else float("nan"),
            "observed_max": float(observed.max()) if len(observed) else float("nan"),
            "feature_unit": str(feature_rows["feature_unit"].iloc[0]) if len(feature_rows) and "feature_unit" in feature_rows else "",
            "feature_definition": str(feature_rows["feature_definition"].iloc[0]) if len(feature_rows) and "feature_definition" in feature_rows else "",
            "raw_channel": str(feature_rows["raw_channel"].iloc[0]) if len(feature_rows) and "raw_channel" in feature_rows else feature.removesuffix("_change"),
            "raw_channel_unit": str(feature_rows["raw_channel_unit"].iloc[0]) if len(feature_rows) and "raw_channel_unit" in feature_rows else "",
            "raw_channel_value_min": float(raw_values.min()) if len(raw_values) else float("nan"),
            "raw_channel_value_max": float(raw_values.max()) if len(raw_values) else float("nan"),
            "local_reference_median": float(reference_values.median()) if len(reference_values) else float("nan"),
            "configured_threshold": float(part["configured_threshold"].iloc[0]) if "configured_threshold" in part else float("nan"),
            "configured_contamination": float(part["configured_contamination"].iloc[0]) if "configured_contamination" in part else float("nan"),
            "brake_context": brake_context,
            "gear_context": ", ".join(map(str, gears)) if gears else "unavailable",
            "max_score": float(part["anomaly_score"].max()),
            "explanation": str(explanation),
        }
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def sensitivity_analysis(telemetry: pd.DataFrame, *, window: int = 31, random_state: int = 42) -> pd.DataFrame:
    """Compare real-lap flags across fixed, disclosed settings; this is not validation."""
    windows = sorted({max(5, window // 2), window, min(101, window * 2)})
    configurations = [
        ("Statistical baseline", threshold, 0.03, candidate_window)
        for candidate_window in windows
        for threshold in (4.0, 6.0, 8.0)
    ] + [
        ("Isolation Forest", 6.0, contamination, window)
        for contamination in (0.01, 0.03, 0.08)
    ]
    evaluated = []
    for method, threshold, contamination, candidate_window in configurations:
        result = analyze_telemetry(
            telemetry,
            method=method,
            threshold=threshold,
            contamination=contamination,
            window=candidate_window,
            random_state=random_state,
        )
        segments = summarize_anomaly_segments(result.samples)
        evaluated.append((method, threshold, contamination, candidate_window, result, segments))

    rows = []
    for method, threshold, contamination, candidate_window, result, segments in evaluated:
        peers = [part for other_method, _, _, _, _, part in evaluated if other_method == method and part is not segments]
        centers = ((segments["distance_start_m"] + segments["distance_end_m"]) / 2).tolist()
        stable = bool(centers) and any(
            abs(center - other_center) <= 100.0
            for peer in peers
            for other_center in ((peer["distance_start_m"] + peer["distance_end_m"]) / 2).tolist()
            for center in centers
        )
        rows.append({
            "method": method,
            "threshold": threshold if method == "Statistical baseline" else None,
            "contamination": contamination if method == "Isolation Forest" else None,
            "window_samples": candidate_window,
            "flagged_samples": int(result.quality["potential_anomaly_sample_count"]),
            "flagged_segments": int(result.quality["potential_anomaly_segment_count"]),
            "segment_centers_m": centers,
            "any_region_reappears_within_100m_in_same_method": stable,
        })
    return pd.DataFrame(rows)
