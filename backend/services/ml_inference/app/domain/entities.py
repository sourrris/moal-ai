from dataclasses import dataclass
from typing import Any

from risk_common.schemas import ModelMetadata


@dataclass
class LoadedModel:
    metadata: ModelMetadata
    # Stored model instance; type is backend-specific (e.g. TensorFlow model or lightweight numpy-based state).
    model: Any
    scaler_mean: list[float]
    scaler_std: list[float]
