from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings


class EnvironmentalRiskService(ABC):
    @abstractmethod
    async def assess(self, latitude: float, longitude: float) -> dict[str, Any]:
        ...


class MockEnvironmentalRiskService(EnvironmentalRiskService):
    """Safe development fallback: it never pretends to have live weather or
    sanitation observations and therefore never creates a risk alert."""

    async def assess(self, latitude: float, longitude: float) -> dict[str, Any]:
        return {
            "risk_level": "NORMAL",
            "risk_score": 0.0,
            "potential_water_borne_diseases": [],
            "potential_vector_borne_diseases": [],
            "contributing_factors": [],
            "prevention_guidance": [
                "Use safe drinking water and maintain hand hygiene.",
                "Follow local public-health and flood-safety advisories when issued.",
            ],
            "data_status": "NO_LIVE_ENVIRONMENTAL_DATA",
            "assessed_at": datetime.now(timezone.utc),
        }


class ExternalEnvironmentalRiskService(EnvironmentalRiskService):
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def assess(self, latitude: float, longitude: float) -> dict[str, Any]:
        response = await self._client.post(
            settings.ENVIRONMENTAL_RISK_SERVICE_URL,
            json={"latitude": latitude, "longitude": longitude},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        # The external model must return this documented response shape. The
        # API layer validates it before it reaches a user.
        data.setdefault("assessed_at", datetime.now(timezone.utc))
        data.setdefault("data_status", "LIVE_ENVIRONMENTAL_MODEL")
        return data


class EnvironmentalRiskServiceRegistry:
    def __init__(self) -> None:
        self._service: EnvironmentalRiskService | None = None
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        if settings.ENVIRONMENTAL_RISK_MODE == "external":
            self._client = httpx.AsyncClient()
            self._service = ExternalEnvironmentalRiskService(self._client)
        else:
            self._service = MockEnvironmentalRiskService()

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None
        self._service = None

    @property
    def service(self) -> EnvironmentalRiskService:
        if self._service is None:
            raise RuntimeError("Environmental risk service not initialized")
        return self._service


environmental_risk_registry = EnvironmentalRiskServiceRegistry()
