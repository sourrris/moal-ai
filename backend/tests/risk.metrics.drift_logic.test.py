"""Unit tests for feature-distribution drift snapshot scoring."""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "risk"
    / "metrics"
    / "app"
    / "application"
    / "aggregator.py"
)
SPEC = importlib.util.spec_from_file_location("risk_metrics_module", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load metrics aggregator module for drift tests")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_build_feature_distribution_snapshots = MODULE._build_feature_distribution_snapshots


def test_feature_distribution_drift_produces_sorted_top_contributors() -> None:
    bucket = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        {
            "tenant_id": "tenant-alpha",
            "model_name": "risk_autoencoder",
            "model_version": "20260301100000",
            "feature_idx": 0,
            "recent_feature_count": 120,
            "recent_mean": 2.0,
            "recent_std": 1.0,
            "baseline_feature_count": 160,
            "baseline_mean": 0.0,
            "baseline_std": 0.5,
            "recent_decision_count": 120,
            "baseline_decision_count": 160,
        },
        {
            "tenant_id": "tenant-alpha",
            "model_name": "risk_autoencoder",
            "model_version": "20260301100000",
            "feature_idx": 1,
            "recent_feature_count": 120,
            "recent_mean": 0.2,
            "recent_std": 0.5,
            "baseline_feature_count": 160,
            "baseline_mean": 0.1,
            "baseline_std": 0.4,
            "recent_decision_count": 120,
            "baseline_decision_count": 160,
        },
    ]

    snapshots = _build_feature_distribution_snapshots(rows, bucket)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["drift_status"] in {"stable", "degraded", "critical"}
    top_contributors = snapshot["details"]["top_contributors"]
    assert len(top_contributors) == 2
    assert top_contributors[0]["score"] >= top_contributors[1]["score"]
    assert snapshot["details"]["method"] == "feature_distribution_shift"
    assert snapshot["details"]["baseline_source"] in {"window_baseline", "training_preprocessing"}


def test_feature_distribution_drift_respects_minimum_sample_gates() -> None:
    bucket = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        {
            "tenant_id": "tenant-alpha",
            "model_name": "risk_autoencoder",
            "model_version": "20260301100000",
            "feature_idx": 0,
            "recent_feature_count": 5,
            "recent_mean": 2.0,
            "recent_std": 1.0,
            "baseline_feature_count": 20,
            "baseline_mean": 0.0,
            "baseline_std": 0.5,
            "recent_decision_count": 20,
            "baseline_decision_count": 90,
        }
    ]

    snapshots = _build_feature_distribution_snapshots(rows, bucket)
    assert snapshots == []


def test_feature_distribution_drift_uses_training_preprocessing_when_available() -> None:
    bucket = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        {
            "tenant_id": "tenant-alpha",
            "model_name": "risk_autoencoder",
            "model_version": "20260301100000",
            "feature_idx": 0,
            "recent_feature_count": 120,
            "recent_mean": 1.5,
            "recent_std": 1.1,
            "baseline_feature_count": 0,
            "baseline_mean": 0.0,
            "baseline_std": 0.0,
            "recent_decision_count": 120,
            "baseline_decision_count": 0,
            "training_mean": [0.2, 0.3],
            "training_std": [0.4, 0.5],
            "training_sample_count": 160,
        }
    ]

    snapshots = _build_feature_distribution_snapshots(rows, bucket)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["details"]["baseline_source"] == "training_preprocessing"
    contributor = snapshot["details"]["top_contributors"][0]
    assert contributor["baseline_source"] == "training_preprocessing"
    assert contributor["baseline_mean"] == 0.2
    assert contributor["baseline_std"] == 0.4
