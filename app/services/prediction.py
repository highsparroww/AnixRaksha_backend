import random
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import settings
from app.models.enums import Disease

WATER_BORNE_DISEASES = [d.value for d in Disease]

_GENERAL_PRECAUTIONS = [
    "Use safe, boiled, filtered, or treated drinking water.",
    "Wash hands with soap before eating and after using the toilet.",
    "Avoid food or water that may be contaminated.",
    "Seek medical evaluation promptly if symptoms are severe, persistent, or worsening.",
]

_DISEASE_PRECAUTIONS: dict[str, list[str]] = {
    "CHOLERA": _GENERAL_PRECAUTIONS,
    "TYPHOID": [
        "Use safe, boiled, filtered, or treated drinking water.",
        "Eat thoroughly cooked food and avoid raw food from uncertain sources.",
        "Wash hands with soap before preparing or eating food.",
        "Seek medical evaluation promptly; only a clinician can confirm the cause of symptoms.",
    ],
    "HEPATITIS_A": [
        "Use safe drinking water and maintain careful hand hygiene.",
        "Avoid raw or undercooked food from uncertain sources.",
        "Do not share food-preparation duties when unwell without strict hand hygiene.",
        "Seek medical evaluation promptly if symptoms persist or worsen.",
    ],
    "HEPATITIS_E": [
        "Use safe drinking water and maintain careful hand hygiene.",
        "Avoid food and water from potentially contaminated sources.",
        "Seek medical evaluation promptly, especially during pregnancy or if symptoms are severe.",
    ],
    "DYSENTERY": _GENERAL_PRECAUTIONS,
    "ROTAVIRUS": _GENERAL_PRECAUTIONS,
    "OTHER_WATER_BORNE": _GENERAL_PRECAUTIONS,
}


def precautions_for_disease(disease: str) -> list[str]:
    """General public-health education, deliberately not personalised advice."""
    return list(_DISEASE_PRECAUTIONS.get(disease, _GENERAL_PRECAUTIONS))

# very small illustrative symptom -> disease weighting for the mock model.
_SYMPTOM_WEIGHTS: dict[str, dict[str, float]] = {
    "DIARRHEA": {"CHOLERA": 0.35, "DYSENTERY": 0.25, "ROTAVIRUS": 0.2, "TYPHOID": 0.1},
    "VOMITING": {"CHOLERA": 0.25, "ROTAVIRUS": 0.3, "TYPHOID": 0.1},
    "FEVER": {"TYPHOID": 0.35, "HEPATITIS_A": 0.15, "HEPATITIS_E": 0.15},
    "DEHYDRATION": {"CHOLERA": 0.3, "ROTAVIRUS": 0.2},
    "BLOOD_IN_STOOL": {"DYSENTERY": 0.45},
    "ABDOMINAL_PAIN": {"TYPHOID": 0.15, "DYSENTERY": 0.15, "HEPATITIS_A": 0.1},
    "NAUSEA": {"HEPATITIS_A": 0.2, "HEPATITIS_E": 0.2},
    "HEADACHE": {"TYPHOID": 0.1},
    "WEAKNESS": {"HEPATITIS_A": 0.1, "HEPATITIS_E": 0.1},
    "MUSCLE_CRAMPS": {"CHOLERA": 0.15},
}


class PredictionService(ABC):
    @abstractmethod
    async def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def health(self) -> dict[str, Any]:
        return {"status": "ok"}


class MockPredictionService(PredictionService):
    """Deterministic-ish mock model so the demo is repeatable enough to be
    convincing without needing a real ML model."""

    MODEL_VERSION = "mock-v1"

    async def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        symptoms: list[str] = payload.get("symptoms", [])
        scores: dict[str, float] = {d: 0.05 for d in WATER_BORNE_DISEASES}
        for symptom in symptoms:
            for disease, weight in _SYMPTOM_WEIGHTS.get(symptom, {}).items():
                scores[disease] = scores.get(disease, 0.0) + weight

        severity = (payload.get("severity") or "MILD").upper()
        severity_boost = {"MILD": 0.0, "MODERATE": 0.05, "SEVERE": 0.12}.get(severity, 0.0)
        temperature = payload.get("temperature") or 37.0
        if temperature and temperature >= 38.0:
            scores["TYPHOID"] = scores.get("TYPHOID", 0) + 0.1
            scores["HEPATITIS_A"] = scores.get("HEPATITIS_A", 0) + 0.05

        for k in scores:
            scores[k] += severity_boost

        if not symptoms or max(scores.values()) <= 0.06:
            best_disease = "OTHER_WATER_BORNE"
            confidence = round(random.uniform(0.3, 0.5), 2)
        else:
            best_disease = max(scores, key=scores.get)
            raw = scores[best_disease]
            confidence = round(min(0.97, max(0.4, raw + random.uniform(-0.05, 0.05))), 2)

        return {
            "predicted_disease": best_disease,
            "is_water_borne": True,
            "confidence": confidence,
            "model_version": self.MODEL_VERSION,
        }

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "mode": "mock"}


class ExternalMLPredictionService(PredictionService):
    """Calls an externally hosted ML model over HTTP using a single reusable
    async client (created once, reused across requests)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(settings.ML_SERVICE_URL, json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()

    async def health(self) -> dict[str, Any]:
        try:
            url = settings.ML_SERVICE_URL.rsplit("/predict", 1)[0] + "/health"
            response = await self._client.get(url, timeout=3.0)
            if response.status_code == 200:
                return {"status": "ok", "mode": "external"}
            return {"status": "degraded", "mode": "external"}
        except Exception:
            return {"status": "unreachable", "mode": "external"}


class PredictionServiceRegistry:
    """Holds a single persistent instance of the configured prediction
    service, created once on startup."""

    def __init__(self) -> None:
        self._service: PredictionService | None = None
        self._http_client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        if settings.ML_MODE == "external":
            self._http_client = httpx.AsyncClient()
            self._service = ExternalMLPredictionService(self._http_client)
        else:
            self._service = MockPredictionService()

    async def shutdown(self) -> None:
        if self._http_client:
            await self._http_client.aclose()

    @property
    def service(self) -> PredictionService:
        if self._service is None:
            raise RuntimeError("Prediction service not initialized")
        return self._service


prediction_registry = PredictionServiceRegistry()
