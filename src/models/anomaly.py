"""Statistical baseline and Isolation Forest for synthetic sensor anomalies."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score, precision_score, recall_score


@dataclass
class EvaluationResult:
    """Held-out predictions, metric comparison, and chronological split point."""
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    split_index: int
    train_normal_count: int


def _robust_location_scale(train: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    center = train.median()
    scale = 1.4826 * (train.sub(center).abs().median())
    # Fall back for constant/near-constant MAD distributions.
    std = train.std(ddof=0).replace(0, np.nan)
    scale = scale.where(scale > 0, std).fillna(1e-12)
    return center, scale


def statistical_baseline(
    train_normal: pd.DataFrame,
    test: pd.DataFrame,
    *,
    threshold: float = 3.5,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Flag a row if any signal exceeds a train-fitted robust z threshold.

    Returns binary flags and per-row text explaining signal deviations.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    center, scale = _robust_location_scale(train_normal)
    z = test.sub(center).div(scale).abs()
    flags = z.gt(threshold).any(axis=1).to_numpy(dtype=np.int8)
    reasons = []
    for _, row in z.iterrows():
        significant = [f"{col}: {value:.2f} robust-z (>{threshold:g})"
                       for col, value in row.items() if value > threshold]
        reasons.append("; ".join(significant) if significant else "no signal exceeded threshold")
    return flags, pd.DataFrame({"baseline_reason": reasons}, index=test.index)


def evaluate_anomaly_methods(
    frame: pd.DataFrame,
    *,
    feature_cols: list[str],
    label_col: str = "anomaly_label",
    time_col: str | None = "timestamp",
    test_fraction: float = 0.3,
    threshold: float = 3.5,
    contamination: float = 0.05,
    random_state: int = 42,
) -> EvaluationResult:
    """Compare train-fitted baseline and Isolation Forest on a later time block.

    Rows are split in existing chronological order. Ground-truth labels are
    excluded from model features. For this labelled synthetic benchmark,
    labels in the training block select normal training examples (a best-case
    semi-supervised setup); held-out labels are used only for evaluation.
    """
    if label_col not in frame:
        raise ValueError(f"Ground-truth label column not present: {label_col}")
    if time_col is not None:
        if time_col in feature_cols:
            raise ValueError("Timestamp must not be included as a model feature")
        if time_col not in frame:
            raise ValueError(f"Time column not present: {time_col}")
        times = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        if times.isna().any():
            raise ValueError(f"Time column contains invalid or missing timestamps: {time_col}")
        if not times.is_monotonic_increasing:
            raise ValueError("Rows must be sorted by timestamp before chronological evaluation")
    missing = [c for c in feature_cols if c not in frame]
    if missing:
        raise ValueError(f"Feature columns not present: {missing}")
    if label_col in feature_cols:
        raise ValueError("Ground-truth label must not be included as a model feature")
    if len(feature_cols) == 0:
        raise ValueError("At least one feature column is required")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be in (0, 0.5]")
    data = frame[feature_cols + [label_col]].copy()
    if data.isna().any().any() or not np.isfinite(data[feature_cols].to_numpy(dtype=float)).all():
        raise ValueError("Model inputs and labels must not contain missing/non-finite values")
    raw_labels = data[label_col].to_numpy()
    if not np.isin(raw_labels, [0, 1]).all():
        raise ValueError("Ground-truth labels must be binary 0/1")
    split = int(len(data) * (1 - test_fraction))
    if split < 2 or split >= len(data):
        raise ValueError("Not enough records for chronological train/test split")
    train, test = data.iloc[:split], data.iloc[split:]
    train_normal = train.loc[train[label_col].eq(0), feature_cols]
    if len(train_normal) < 2:
        raise ValueError("Training block must contain at least two labelled normal rows")
    x_test = test[feature_cols]
    y_test = test[label_col].astype(int).to_numpy()

    baseline_flags, reasons = statistical_baseline(train_normal, x_test, threshold=threshold)
    forest = IsolationForest(contamination=contamination, random_state=random_state)
    forest.fit(train_normal)
    forest_flags = (forest.predict(x_test) == -1).astype(np.int8)
    scores = -forest.score_samples(x_test)

    def metric_row(name: str, pred: np.ndarray) -> dict[str, float | str | int]:
        tn = int(((y_test == 0) & (pred == 0)).sum())
        fp = int(((y_test == 0) & (pred == 1)).sum())
        return {
            "model": name,
            "precision": float(precision_score(y_test, pred, zero_division=0)),
            "recall": float(recall_score(y_test, pred, zero_division=0)),
            "f1": float(f1_score(y_test, pred, zero_division=0)),
            "false_positive_rate": fp / (fp + tn) if (fp + tn) else float("nan"),
            "true_positive": int(((y_test == 1) & (pred == 1)).sum()),
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": int(((y_test == 1) & (pred == 0)).sum()),
        }

    predictions = x_test.copy()
    predictions["ground_truth"] = y_test
    predictions["baseline_flag"] = baseline_flags
    predictions["isolation_forest_flag"] = forest_flags
    predictions["isolation_score"] = scores
    predictions["baseline_reason"] = reasons["baseline_reason"].to_numpy()
    predictions["isolation_reason"] = np.where(
        forest_flags == 1,
        "Isolation Forest score exceeds its train-fitted decision boundary; inspect signal values",
        "Isolation Forest score is within its train-fitted decision boundary",
    )
    metrics = pd.DataFrame([
        metric_row("Statistical robust-z baseline", baseline_flags),
        metric_row("Isolation Forest", forest_flags),
    ])
    return EvaluationResult(predictions, metrics, split, len(train_normal))
