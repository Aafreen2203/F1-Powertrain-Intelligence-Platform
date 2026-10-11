"""In-memory export helpers for a real FastF1 lap-comparison case study."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

LAP_COMPARISON_SOURCE = "PUBLIC FASTF1 TELEMETRY · LAP COMPARISON"


def lap_comparison_exports(
    summary: pd.DataFrame,
    *,
    metadata: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Return a source-labelled comparison CSV frame and evidence report."""
    export = summary.copy(deep=True)
    retrieval = metadata.get("retrieval")
    if not isinstance(retrieval, dict):
        retrieval = {}
    export.insert(0, "data_source", LAP_COMPARISON_SOURCE)
    for key in ("year", "event", "session", "driver", "reference_lap"):
        export.insert(1, key, metadata.get(key))
    export["comparison_laps"] = json.dumps(metadata.get("comparison_laps", []))
    export["alignment_method"] = metadata.get("alignment_method", "unavailable")
    export["session_load_completed_at_utc"] = retrieval.get("load_completed_at_utc")
    export["cache_network_origin"] = retrieval.get("cache_origin", "unknown")
    export["lap_conditions_json"] = json.dumps(
        metadata.get("lap_context", []), default=str, sort_keys=True
    )
    export["telemetry_quality_json"] = json.dumps(
        metadata.get("telemetry_quality", {}), default=str, sort_keys=True
    )

    lines = [
        "# Public FastF1 Lap Comparison",
        "",
        f"> Data source: {LAP_COMPARISON_SOURCE}. Observational comparison; no power-unit fault inference.",
        "",
        "## Selection and method",
    ]
    for key in ("year", "event", "session", "driver", "reference_lap", "comparison_laps"):
        lines.append(f"- {key.replace('_', ' ').title()}: {metadata.get(key, 'unavailable')}")
    lines.extend([
        f"- Alignment: {metadata.get('alignment_method', 'unavailable')}",
        "- Interpretation sign: comparison lap minus reference lap.",
        f"- Selected lap conditions: {json.dumps(metadata.get('lap_context', []), default=str, sort_keys=True)}",
        f"- Telemetry quality checks: {json.dumps(metadata.get('telemetry_quality', {}), default=str, sort_keys=True)}",
    ])
    lines.extend([
        f"- Load completed UTC: {retrieval.get('load_completed_at_utc', 'unavailable')}",
        f"- Cache/network origin: {retrieval.get('cache_origin', 'unknown')}",
    ])
    lines.extend([
        "",
        "## Calculated channel differences",
        "",
    ])
    if export.empty:
        lines.append("No comparable continuous channel results were available.")
    else:
        lines.append("| Comparison lap | Channel | Distance (m) | Reference | Comparison | Delta (comparison − reference) | Valid aligned samples | Grid coverage | Mean absolute difference |")
        lines.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in summary.itertuples(index=False):
            lines.append(
                f"| {getattr(row, 'comparison_lap')} | {getattr(row, 'channel')} | "
                f"{getattr(row, 'distance_m'):.2f} | {getattr(row, 'reference_value'):.3f} | "
                f"{getattr(row, 'comparison_value'):.3f} | "
                f"{getattr(row, 'delta_comparison_minus_reference'):+.3f} | "
                f"{getattr(row, 'valid_aligned_samples')} / {getattr(row, 'aligned_grid_samples')} | "
                f"{getattr(row, 'coverage_fraction'):.1%} | "
                f"{getattr(row, 'mean_absolute_difference'):.3f} |"
            )
    lines.extend([
        "",
        "## Limits and next checks",
        "Differences are distance-aligned interpolated observations. Raw provider traces remain separate; the grid uses linear interpolation for continuous signals and nearest samples for Brake/gear. Missing gaps are not bridged and no values are extrapolated.",
        "Tyre, weather, traffic, track status, driver inputs, and session evolution can explain differences. FastF1 public telemetry is not the full internal power-unit sensor suite and does not establish a fault.",
        "Inspect native samples around flagged locations and compare additional clean laps with tyre and session-condition context.",
    ])
    return export, "\n".join(lines) + "\n"
