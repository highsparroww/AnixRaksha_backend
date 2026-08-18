"""Internal foundation for environmental disease-risk modelling.

This module deliberately contains no patient-facing routes, alert dispatch, or
medical inference. Providers supply observations, the pipeline validates and
stores model features, and a future model may return explainable risk results.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import EnvironmentalObservation
from app.schemas.schemas import EnvironmentalDiseaseRiskResult, EnvironmentalFeatureSet
from app.services.geo import make_point


class EnvironmentalDataProvider(ABC):
    @abstractmethod
    async def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Return source data only; no disease interpretation belongs here."""


class UnavailableEnvironmentalDataProvider(EnvironmentalDataProvider):
    """Development-safe provider that makes no claim about live conditions."""

    async def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        return {
            "source": "unavailable",
            "observed_at": datetime.now(timezone.utc),
            "data_status": "UNAVAILABLE",
        }


class ExternalEnvironmentalDataProvider(EnvironmentalDataProvider):
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        response = await self._client.post(
            settings.ENVIRONMENTAL_DATA_SERVICE_URL,
            json={"latitude": latitude, "longitude": longitude},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()


def normalize_environmental_features(
    raw_data: dict[str, Any], latitude: float, longitude: float
) -> EnvironmentalFeatureSet:
    """Validate provider data and map it into the stable model-feature contract.

    Unknown provider fields are retained as additional signals rather than
    being treated as evidence of a disease.
    """
    known_fields = {
        "rainfall_mm_24h", "temperature_c", "humidity_percent", "flood_status",
        "water_quality_status", "sanitation_status",
    }
    try:
        return EnvironmentalFeatureSet(
            latitude=latitude,
            longitude=longitude,
            observed_at=raw_data.get("observed_at", datetime.now(timezone.utc)),
            source=raw_data.get("source", "unknown"),
            rainfall_mm_24h=raw_data.get("rainfall_mm_24h"),
            temperature_c=raw_data.get("temperature_c"),
            humidity_percent=raw_data.get("humidity_percent"),
            flood_status=raw_data.get("flood_status"),
            water_quality_status=raw_data.get("water_quality_status"),
            sanitation_status=raw_data.get("sanitation_status"),
            additional_signals={key: value for key, value in raw_data.items() if key not in known_fields | {"source", "observed_at", "data_status"}},
            data_status=raw_data.get("data_status", "AVAILABLE"),
        )
    except ValidationError as exc:
        raise ValueError("Environmental provider returned invalid feature data") from exc


class DiseaseRiskModel(Protocol):
    async def infer(
        self, features: EnvironmentalFeatureSet, local_case_context: dict[str, Any]
    ) -> list[EnvironmentalDiseaseRiskResult]: ...


class NoopDiseaseRiskModel:
    """Placeholder until an evaluated, disease-specific model is integrated."""

    async def infer(
        self, features: EnvironmentalFeatureSet, local_case_context: dict[str, Any]
    ) -> list[EnvironmentalDiseaseRiskResult]:
        return []


class EnvironmentalPipeline:
    def __init__(self, provider: EnvironmentalDataProvider, model: DiseaseRiskModel | None = None) -> None:
        self.provider = provider
        self.model = model or NoopDiseaseRiskModel()

    async def ingest_and_store(
        self, db: AsyncSession, latitude: float, longitude: float
    ) -> EnvironmentalObservation:
        raw_data = await self.provider.fetch(latitude, longitude)
        features = normalize_environmental_features(raw_data, latitude, longitude)
        observation = EnvironmentalObservation(
            source=features.source,
            location=make_point(latitude, longitude),
            latitude=latitude,
            longitude=longitude,
            observed_at=features.observed_at,
            raw_data=raw_data,
            normalized_features=features.model_dump(mode="json"),
        )
        db.add(observation)
        await db.flush()
        return observation

    async def evaluate(
        self, features: EnvironmentalFeatureSet, local_case_context: dict[str, Any]
    ) -> list[EnvironmentalDiseaseRiskResult]:
        """Future surveillance jobs can pass results to alert policy explicitly."""
        return await self.model.infer(features, local_case_context)


class EnvironmentalPipelineRegistry:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._pipeline: EnvironmentalPipeline | None = None

    async def startup(self) -> None:
        if settings.ENVIRONMENTAL_DATA_MODE == "external":
            self._client = httpx.AsyncClient()
            provider: EnvironmentalDataProvider = ExternalEnvironmentalDataProvider(self._client)
        else:
            provider = UnavailableEnvironmentalDataProvider()
        self._pipeline = EnvironmentalPipeline(provider)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None
        self._pipeline = None

    @property
    def pipeline(self) -> EnvironmentalPipeline:
        if self._pipeline is None:
            raise RuntimeError("Environmental pipeline not initialized")
        return self._pipeline


environmental_pipeline_registry = EnvironmentalPipelineRegistry()
