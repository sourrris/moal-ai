import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

from app.domain.entities import LoadedModel
from risk_common.schemas import InferenceResponse, ModelMetadata


class ModelStore:
    def __init__(self, model_dir: str, default_model_name: str):
        self.model_dir = Path(model_dir)
        self.default_model_name = default_model_name
        self.registry_path = self.model_dir / "registry.json"
        self.registry: dict[str, Any] = {"models": {}, "active_key": None}
        self.active: LoadedModel | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.model_dir.mkdir(parents=True, exist_ok=True)

        if self.registry_path.exists():
            self.registry = json.loads(self.registry_path.read_text())
        else:
            await self._bootstrap_default_model()
            return

        active_key = self.registry.get("active_key")
        if not active_key or active_key not in self.registry["models"]:
            await self._bootstrap_default_model()
            return

        await self._load_active(active_key)

    async def infer(self, event_id, features: list[float]) -> InferenceResponse:
        if self.active is None:
            raise RuntimeError("No active model loaded")

        metadata = self.active.metadata
        if len(features) != metadata.feature_dim:
            raise ValueError(f"Feature vector size mismatch: expected {metadata.feature_dim}, got {len(features)}")

        score = await asyncio.to_thread(self._score_features, features)
        return InferenceResponse(
            event_id=event_id,
            model_name=metadata.model_name,
            model_version=metadata.model_version,
            anomaly_score=score,
            threshold=metadata.threshold,
            is_anomaly=score > metadata.threshold,
        )

    async def train(
        self,
        model_name: str,
        features: list[list[float]],
        epochs: int,
        batch_size: int,
    ) -> ModelMetadata:
        if len(features) < 32:
            raise ValueError("At least 32 samples are required for training")

        async with self._lock:
            metadata, model, path = await asyncio.to_thread(
                self._train_sync,
                model_name,
                features,
                epochs,
                batch_size,
            )
            key = f"{metadata.model_name}:{metadata.model_version}"
            self.registry["models"][key] = {
                "metadata": metadata.model_dump(mode="json"),
                "path": str(path),
            }
            self.registry["active_key"] = key
            self._save_registry()
            self.active = LoadedModel(metadata=metadata, model=model)
            return metadata

    async def activate(self, model_name: str, model_version: str) -> ModelMetadata:
        key = f"{model_name}:{model_version}"
        if key not in self.registry["models"]:
            raise ValueError("Requested model version does not exist")

        async with self._lock:
            await self._load_active(key)
            self.registry["active_key"] = key
            self._save_registry()

        if self.active is None:
            raise RuntimeError("Failed to activate model")
        return self.active.metadata

    def get_active_metadata(self) -> ModelMetadata:
        if self.active is None:
            raise RuntimeError("No active model loaded")
        return self.active.metadata

    async def _bootstrap_default_model(self) -> None:
        np.random.seed(7)
        baseline = np.random.normal(0.0, 1.0, size=(512, 8)).astype("float32")
        metadata = await self.train(
            model_name=self.default_model_name,
            features=baseline.tolist(),
            epochs=6,
            batch_size=32,
        )
        self.registry["active_key"] = f"{metadata.model_name}:{metadata.model_version}"
        self._save_registry()

    async def _load_active(self, key: str) -> None:
        model_info = self.registry["models"][key]
        metadata = ModelMetadata(**model_info["metadata"])
        path = Path(model_info["path"])
        model = await asyncio.to_thread(tf.keras.models.load_model, path)
        self.active = LoadedModel(metadata=metadata, model=model)

    def _save_registry(self) -> None:
        self.registry_path.write_text(json.dumps(self.registry, indent=2, default=str))

    def _train_sync(
        self,
        model_name: str,
        features: list[list[float]],
        epochs: int,
        batch_size: int,
    ) -> tuple[ModelMetadata, tf.keras.Model, Path]:
        x = np.asarray(features, dtype="float32")
        if x.ndim != 2:
            raise ValueError("Training data must be a matrix of shape (samples, features)")

        feature_dim = int(x.shape[1])
        model = self._build_autoencoder(feature_dim)

        split_idx = max(int(len(x) * 0.8), 1)
        x_train = x[:split_idx]
        x_val = x[split_idx:] if split_idx < len(x) else x

        model.fit(
            x_train,
            x_train,
            validation_data=(x_val, x_val),
            epochs=max(1, epochs),
            batch_size=max(1, batch_size),
            verbose=0,
        )

        val_recon = model.predict(x_val, verbose=0)
        val_error = np.mean(np.square(x_val - val_recon), axis=1)
        threshold = float(np.quantile(val_error, 0.99))

        version = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        model_path = self.model_dir / f"{model_name}_{version}.keras"
        model.save(model_path)

        metadata = ModelMetadata(
            model_name=model_name,
            model_version=version,
            feature_dim=feature_dim,
            threshold=threshold,
        )
        return metadata, model, model_path

    def _score_features(self, features: list[float]) -> float:
        if self.active is None:
            raise RuntimeError("No active model loaded")

        x = np.asarray(features, dtype="float32").reshape(1, -1)
        recon = self.active.model.predict(x, verbose=0)
        return float(np.mean(np.square(x - recon)))

    @staticmethod
    def _build_autoencoder(input_dim: int) -> tf.keras.Model:
        inputs = tf.keras.Input(shape=(input_dim,))
        enc1 = tf.keras.layers.Dense(max(4, input_dim // 2), activation="relu")(inputs)
        bottleneck = tf.keras.layers.Dense(max(2, input_dim // 4), activation="relu")(enc1)
        dec1 = tf.keras.layers.Dense(max(4, input_dim // 2), activation="relu")(bottleneck)
        outputs = tf.keras.layers.Dense(input_dim, activation="linear")(dec1)

        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        model.compile(optimizer="adam", loss="mse")
        return model
