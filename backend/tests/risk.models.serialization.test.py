"""Model endpoint normalization and train payload compatibility tests."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.api.routes_models import _normalize_model_item
from risk_common.schemas import ModelTrainRequest


def test_model_item_normalizes_decimal_like_strings() -> None:
    raw = {
        "model_name": "risk_autoencoder",
        "model_version": "20260227160612",
        "threshold": "0.9512769335508348",
        "updated_at": "2026-03-01T05:46:34.194083Z",
        "inference_count": "12",
        "anomaly_rate": "0E-20",
        "source": "inference_only",
        "activate_capable": False,
    }

    item = _normalize_model_item(raw, active_name=None, active_version=None)

    assert item.threshold == pytest.approx(0.9512769335508348)
    assert item.inference_count == 12
    assert item.anomaly_rate == 0.0
    assert item.source == "inference_only"
    assert item.activate_capable is False


def test_model_train_request_backwards_compatibility_with_features_payload() -> None:
    payload = ModelTrainRequest.model_validate(
        {
            "model_name": "risk_autoencoder",
            "features": [[0.1] * 8 for _ in range(64)],
            "epochs": 5,
            "batch_size": 16,
        }
    )

    assert payload.training_source == "provided_features"
    assert payload.features is not None
    assert len(payload.features) == 64


def test_model_train_request_requires_features_when_source_is_provided_features() -> None:
    with pytest.raises(ValueError):
        ModelTrainRequest.model_validate(
            {
                "model_name": "risk_autoencoder",
                "training_source": "provided_features",
                "epochs": 5,
                "batch_size": 16,
            }
        )
