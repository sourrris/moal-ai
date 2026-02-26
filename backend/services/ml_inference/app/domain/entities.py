from dataclasses import dataclass

import tensorflow as tf

from risk_common.schemas import ModelMetadata


@dataclass
class LoadedModel:
    metadata: ModelMetadata
    model: tf.keras.Model
