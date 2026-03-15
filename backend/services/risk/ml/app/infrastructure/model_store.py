import asyncio
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf
from risk_common.schemas import InferenceResponse, ModelMetadata, ModelTrainingResult

from app.domain.entities import LoadedModel


class ModelActivationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            **self.details,
        }


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
        threshold_quantile: float = 0.99,
        auto_activate: bool = False,
    ) -> ModelTrainingResult:
        if len(features) < 32:
            raise ValueError("At least 32 samples are required for training")

        async with self._lock:
            metadata, model, path, preprocessing, training_metrics = await asyncio.to_thread(
                self._train_sync,
                model_name,
                features,
                epochs,
                batch_size,
                threshold_quantile,
            )
            key = f"{metadata.model_name}:{metadata.model_version}"
            self.registry["models"][key] = {
                "metadata": metadata.model_dump(mode="json"),
                "path": path.name,
                "preprocessing": preprocessing,
                "training_metrics": training_metrics,
            }

            should_activate = auto_activate or not self.registry.get("active_key")
            if should_activate:
                self.registry["active_key"] = key
                self.active = LoadedModel(
                    metadata=metadata,
                    model=model,
                    scaler_mean=[float(v) for v in preprocessing["mean"]],
                    scaler_std=[float(v) for v in preprocessing["std"]],
                )

            self._save_registry()
            return ModelTrainingResult(
                model_name=metadata.model_name,
                model_version=metadata.model_version,
                feature_dim=metadata.feature_dim,
                threshold=metadata.threshold,
                updated_at=metadata.updated_at,
                sample_count=len(features),
                auto_activated=should_activate,
                training_metrics=training_metrics,
            )

    async def activate(self, model_name: str, model_version: str) -> ModelMetadata:
        key = f"{model_name}:{model_version}"
        if key not in self.registry["models"]:
            raise ModelActivationError(
                "not_registry_model",
                "Requested model version does not exist in registry",
                details={"model_name": model_name, "model_version": model_version},
            )

        model_info = self._validate_registry_entry_for_activation(
            key=key,
            model_name=model_name,
            model_version=model_version,
        )

        async with self._lock:
            try:
                await self._load_active(key)
            except FileNotFoundError as exc:
                raise ModelActivationError(
                    "artifact_missing",
                    "Model artifact is missing or unreadable",
                    details={
                        "model_name": model_name,
                        "model_version": model_version,
                        "artifact_path": str(model_info.get("path") or ""),
                    },
                ) from exc
            except OSError as exc:
                raise ModelActivationError(
                    "artifact_missing",
                    "Model artifact is missing or unreadable",
                    details={
                        "model_name": model_name,
                        "model_version": model_version,
                        "artifact_path": str(model_info.get("path") or ""),
                    },
                ) from exc
            except ValueError as exc:
                raise ModelActivationError(
                    "invalid_metadata",
                    "Model metadata is invalid and cannot be activated",
                    details={"model_name": model_name, "model_version": model_version},
                ) from exc
            self.registry["active_key"] = key
            self._save_registry()

        if self.active is None:
            raise ModelActivationError(
                "invalid_metadata",
                "Model activation completed without an active model in memory",
                details={"model_name": model_name, "model_version": model_version},
            )
        return self.active.metadata

    def _validate_registry_entry_for_activation(
        self,
        *,
        key: str,
        model_name: str,
        model_version: str,
    ) -> dict[str, Any]:
        model_info = self.registry["models"].get(key)
        if not isinstance(model_info, dict):
            raise ModelActivationError(
                "invalid_metadata",
                "Registry entry is malformed",
                details={"key": key},
            )

        metadata_payload = model_info.get("metadata")
        if not isinstance(metadata_payload, dict):
            raise ModelActivationError(
                "invalid_metadata",
                "Registry metadata payload is missing",
                details={"key": key},
            )

        try:
            metadata = ModelMetadata.model_validate(metadata_payload)
        except Exception as exc:  # noqa: BLE001
            raise ModelActivationError(
                "invalid_metadata",
                "Registry metadata payload is invalid",
                details={"key": key},
            ) from exc

        if metadata.model_name != model_name or metadata.model_version != model_version:
            raise ModelActivationError(
                "invalid_metadata",
                "Registry metadata identity mismatch",
                details={
                    "expected_model_name": model_name,
                    "expected_model_version": model_version,
                    "metadata_model_name": metadata.model_name,
                    "metadata_model_version": metadata.model_version,
                },
            )

        if metadata.feature_dim <= 0:
            raise ModelActivationError(
                "invalid_metadata",
                "Model feature dimension is invalid",
                details={"feature_dim": metadata.feature_dim, "key": key},
            )

        if not math.isfinite(float(metadata.threshold)) or float(metadata.threshold) <= 0:
            raise ModelActivationError(
                "invalid_metadata",
                "Model threshold is invalid",
                details={"threshold": metadata.threshold, "key": key},
            )

        model_path = self._resolve_model_path(str(model_info.get("path") or ""))
        if not model_path.exists() or not model_path.is_file():
            raise ModelActivationError(
                "artifact_missing",
                "Model artifact file does not exist",
                details={"artifact_path": str(model_path), "key": key},
            )
        try:
            with model_path.open("rb"):
                pass
        except OSError as exc:
            raise ModelActivationError(
                "artifact_missing",
                "Model artifact file is not readable",
                details={"artifact_path": str(model_path), "key": key},
            ) from exc

        preprocessing = model_info.get("preprocessing") or {}
        mean = preprocessing.get("mean") if isinstance(preprocessing, dict) else None
        std = preprocessing.get("std") if isinstance(preprocessing, dict) else None
        if mean is not None and not isinstance(mean, list):
            raise ModelActivationError(
                "invalid_metadata",
                "Preprocessing mean payload must be a list",
                details={"key": key},
            )
        if std is not None and not isinstance(std, list):
            raise ModelActivationError(
                "invalid_metadata",
                "Preprocessing std payload must be a list",
                details={"key": key},
            )
        if isinstance(mean, list) and len(mean) != metadata.feature_dim:
            raise ModelActivationError(
                "invalid_metadata",
                "Preprocessing mean length does not match feature dimension",
                details={"feature_dim": metadata.feature_dim, "mean_length": len(mean), "key": key},
            )
        if isinstance(std, list) and len(std) != metadata.feature_dim:
            raise ModelActivationError(
                "invalid_metadata",
                "Preprocessing std length does not match feature dimension",
                details={"feature_dim": metadata.feature_dim, "std_length": len(std), "key": key},
            )

        return model_info

    def get_active_metadata(self) -> ModelMetadata:
        if self.active is None:
            raise RuntimeError("No active model loaded")
        return self.active.metadata

    def list_models(self) -> list[ModelMetadata]:
        return [ModelMetadata(**m["metadata"]) for m in self.registry["models"].values()]

    async def _bootstrap_default_model(self) -> None:
        np.random.seed(7)
        baseline = np.random.normal(0.0, 1.0, size=(512, 8)).astype("float32")
        result = await self.train(
            model_name=self.default_model_name,
            features=baseline.tolist(),
            epochs=6,
            batch_size=32,
            threshold_quantile=0.99,
            auto_activate=True,
        )
        self.registry["active_key"] = f"{result.model_name}:{result.model_version}"
        self._save_registry()

    async def _load_active(self, key: str) -> None:
        model_info = self.registry["models"][key]
        metadata = ModelMetadata(**model_info["metadata"])
        path = self._resolve_model_path(model_info["path"])
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Model artifact does not exist: {path}")
        model = await asyncio.to_thread(tf.keras.models.load_model, path)
        preprocessing = model_info.get("preprocessing") or {}
        mean = preprocessing.get("mean") or [0.0] * metadata.feature_dim
        std = preprocessing.get("std") or [1.0] * metadata.feature_dim

        # Backward compatibility for older registry entries without preprocessing state.
        if len(mean) != metadata.feature_dim:
            mean = [0.0] * metadata.feature_dim
        if len(std) != metadata.feature_dim:
            std = [1.0] * metadata.feature_dim

        self.active = LoadedModel(
            metadata=metadata,
            model=model,
            scaler_mean=[float(v) for v in mean],
            scaler_std=[float(v if float(v) != 0.0 else 1.0) for v in std],
        )

    def _resolve_model_path(self, path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return (self.model_dir / path).resolve()

    def _save_registry(self) -> None:
        self.registry_path.write_text(json.dumps(self.registry, indent=2, default=str))

    def _train_sync(
        self,
        model_name: str,
        features: list[list[float]],
        epochs: int,
        batch_size: int,
        threshold_quantile: float,
    ) -> tuple[ModelMetadata, tf.keras.Model, Path, dict[str, Any], dict[str, Any]]:
        started = time.perf_counter()
        x = np.asarray(features, dtype="float32")
        if x.ndim != 2:
            raise ValueError("Training data must be a matrix of shape (samples, features)")

        if x.shape[0] < 32:
            raise ValueError("At least 32 samples are required for training")

        feature_dim = int(x.shape[1])
        train_mean = np.mean(x, axis=0).astype("float32")
        train_std = np.std(x, axis=0).astype("float32")
        train_std = np.where(train_std < 1e-6, 1.0, train_std)
        x_norm = (x - train_mean) / train_std

        model = self._build_autoencoder(feature_dim)

        split_idx = max(int(len(x_norm) * 0.8), 1)
        x_train = x_norm[:split_idx]
        x_val = x_norm[split_idx:] if split_idx < len(x_norm) else x_norm

        history = model.fit(
            x_train,
            x_train,
            validation_data=(x_val, x_val),
            epochs=max(1, epochs),
            batch_size=max(1, batch_size),
            verbose=0,
        )

        val_recon = model.predict(x_val, verbose=0)
        val_error = np.mean(np.square(x_val - val_recon), axis=1)
        clamped_quantile = float(np.clip(threshold_quantile, 0.5, 0.9999))
        threshold = float(np.quantile(val_error, clamped_quantile))

        version = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        model_path = self.model_dir / f"{model_name}_{version}.keras"
        model.save(model_path)

        history_loss = history.history.get("loss") or [float(np.mean(val_error))]
        history_val_loss = history.history.get("val_loss") or history_loss
        training_metrics = {
            "train_loss": float(history_loss[-1]),
            "val_loss": float(history_val_loss[-1]),
            "reconstruction_error_quantiles": {
                "p50": float(np.quantile(val_error, 0.50)),
                "p90": float(np.quantile(val_error, 0.90)),
                "p95": float(np.quantile(val_error, 0.95)),
                "p99": float(np.quantile(val_error, 0.99)),
            },
            "threshold_quantile": clamped_quantile,
            "threshold": threshold,
            "sample_count": int(x.shape[0]),
            "feature_dim": feature_dim,
            "duration_seconds": round(float(time.perf_counter() - started), 4),
            "preprocessing": {
                "type": "zscore",
                "mean": [float(v) for v in train_mean.tolist()],
                "std": [float(v) for v in train_std.tolist()],
            },
        }
        preprocessing = {
            "type": "zscore",
            "mean": [float(v) for v in train_mean.tolist()],
            "std": [float(v) for v in train_std.tolist()],
        }

        metadata = ModelMetadata(
            model_name=model_name,
            model_version=version,
            feature_dim=feature_dim,
            threshold=threshold,
        )
        return metadata, model, model_path, preprocessing, training_metrics

    def _score_features(self, features: list[float]) -> float:
        if self.active is None:
            raise RuntimeError("No active model loaded")

        x = np.asarray(features, dtype="float32").reshape(1, -1)
        mean = np.asarray(self.active.scaler_mean, dtype="float32").reshape(1, -1)
        std = np.asarray(self.active.scaler_std, dtype="float32").reshape(1, -1)
        std = np.where(std < 1e-6, 1.0, std)

        x_norm = (x - mean) / std
        recon = self.active.model.predict(x_norm, verbose=0)
        return float(np.mean(np.square(x_norm - recon)))

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
