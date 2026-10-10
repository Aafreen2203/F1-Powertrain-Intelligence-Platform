"""In-memory exports for exploratory real FastF1 telemetry analysis."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.analytics.telemetry_anomaly import TelemetryAnomalyResult, summarize_anomaly_segments

PUBLIC_SOURCE = "PUBLIC FASTF1 TELEMETRY · UNLABELLED"


def telemetry_export_frames(
    result: TelemetryAnomalyResult,
    *,
    metadata: dict[str, Any],
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Build downloadable sample, quality, and Markdown report artifacts.

    The helper does not write files. Streamlit download buttons are the explicit
    export destination, keeping data out of project folders by default.
    """
    identifiers = {
        "data_source": PUBLIC_SOURCE,
        "year": metadata.get("year"),
        "event": metadata.get("event"),
        "session": metadata.get("session"),
        "driver": metadata.get("driver"),
        "lap": metadata.get("lap"),
        "detection_method": result.method,
        "threshold": parameters.get("threshold"),
        "contamination": parameters.get("contamination"),
        "context_window_samples": parameters.get("window"),
    }
    sample_frame = result.samples.copy()
    for column, value in reversed(list(identifiers.items())):
        sample_frame.insert(0, column, value)
    quality_rows = [
        {"data_source": PUBLIC_SOURCE, "check": key,
         "value": json.dumps(value, default=str, sort_keys=True)}
        for key, value in result.quality.items()
    ]
    quality_frame = pd.DataFrame(quality_rows)
    segments = summarize_anomaly_segments(result.samples)
    lines = [
        "# Public FastF1 Telemetry Anomaly Review",
        "",
        f"> Data source: {PUBLIC_SOURCE}. This lap has no verified anomaly labels.",
        "",
        "## Selection and method",
    ]
    lines.extend(f"- {key.title()}: {value}" for key, value in metadata.items())
    lines.extend([
        f"- Method: {result.method}",
        f"- Parameters: {json.dumps(parameters, sort_keys=True)}",
        f"- Available channels: {', '.join(result.available_channels)}",
        f"- Channel availability: {json.dumps(result.quality.get('channel_availability', {}), sort_keys=True)}",
        f"- Detection note: {result.quality['method_note']}",
        "",
        "## Data quality and findings",
        f"- Usable samples: {result.quality['rows_used']}",
        f"- Potential anomaly samples: {result.quality['potential_anomaly_sample_count']}",
        f"- Potential contiguous segments: {result.quality['potential_anomaly_segment_count']}",
        f"- Data quality warnings: {', '.join(result.quality.get('warnings', [])) or 'None reported'}",
        "",
    ])
    if segments.empty:
        lines.append("No samples met the selected rule on this lap.")
    else:
        lines.extend([
            "| Segment | Samples | Distance range (m) | Main feature | Maximum score |",
            "| ---: | ---: | ---: | --- | ---: |",
        ])
        for row in segments.itertuples(index=False):
            lines.append(
                f"| {row.segment_id} | {row.sample_count} | {row.distance_start_m:.2f}–"
                f"{row.distance_end_m:.2f} | {row.top_feature} | {row.max_score:.3f} |"
            )
    lines.extend([
        "",
        "## Interpretation limits",
        "Flags identify potentially unusual telemetry for investigation; they are not confirmed faults.",
        "FastF1 telemetry is unlabelled and may reflect braking, shifts, cornering, driver inputs, or race context.",
        "No precision, recall, F1, accuracy, false-positive rate, or engine-failure prediction is claimed.",
        "Isolation Forest results, when selected, are fit and scored on this same lap and are exploratory, not out-of-sample.",
        "No missing telemetry channels or values are filled with synthetic readings.",
    ])
    return sample_frame, quality_frame, "\n".join(lines) + "\n"
