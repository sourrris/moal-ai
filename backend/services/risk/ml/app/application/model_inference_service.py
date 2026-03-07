from app.infrastructure.model_store import ModelStore
from app.application.standardized_pipeline import StandardizedInferenceRequest, derive_features
from risk_common.schemas import InferenceRequest, InferenceResponse, ModelMetadata, ModelTrainingResult, ModelTrainRequest


class InferenceService:
    def __init__(self, model_store: ModelStore):
        self.model_store = model_store

    async def infer(self, payload: InferenceRequest) -> InferenceResponse:
        return await self.model_store.infer(event_id=payload.event_id, features=payload.features)

    async def infer_standardized(self, payload: StandardizedInferenceRequest) -> InferenceResponse:
        features = payload.features or derive_features(payload.transaction)
        return await self.model_store.infer(event_id=payload.event_id, features=features)

    async def train(self, payload: ModelTrainRequest) -> ModelTrainingResult:
        if not payload.features:
            raise ValueError("No training features were provided")
        return await self.model_store.train(
            model_name=payload.model_name,
            features=payload.features,
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            threshold_quantile=payload.threshold_quantile,
            auto_activate=payload.auto_activate,
        )

    async def activate(self, model_name: str, model_version: str) -> ModelMetadata:
        return await self.model_store.activate(model_name=model_name, model_version=model_version)

    def list_models(self) -> list[ModelMetadata]:
        return self.model_store.list_models()

    def get_active(self) -> ModelMetadata:
        return self.model_store.get_active_metadata()
