from datetime import datetime, timezone

import pytest

from app.services.environmental_pipeline import (
    EnvironmentalDataProvider,
    EnvironmentalPipeline,
    UnavailableEnvironmentalDataProvider,
    normalize_environmental_features,
)


def test_normalization_preserves_unknown_signals_without_disease_claims():
    features = normalize_environmental_features(
        {
            "source": "weather-provider",
            "observed_at": datetime.now(timezone.utc),
            "rainfall_mm_24h": 20.5,
            "humidity_percent": 80,
            "provider_quality_code": "verified",
        },
        26.45,
        80.33,
    )
    assert features.rainfall_mm_24h == 20.5
    assert features.additional_signals == {"provider_quality_code": "verified"}


@pytest.mark.asyncio
async def test_noop_pipeline_does_not_create_fake_disease_risk():
    pipeline = EnvironmentalPipeline(UnavailableEnvironmentalDataProvider())
    raw = await pipeline.provider.fetch(26.45, 80.33)
    features = normalize_environmental_features(raw, 26.45, 80.33)
    assert features.data_status == "UNAVAILABLE"
    assert await pipeline.evaluate(features, {"confirmed_cases_7d": 4}) == []


@pytest.mark.asyncio
async def test_pipeline_persists_normalized_model_features(db_session):
    class StaticProvider(EnvironmentalDataProvider):
        async def fetch(self, latitude, longitude):
            return {
                "source": "test-provider", "observed_at": datetime.now(timezone.utc),
                "rainfall_mm_24h": 12.0, "flood_status": "NONE",
            }

    observation = await EnvironmentalPipeline(StaticProvider()).ingest_and_store(db_session, 26.45, 80.33)
    await db_session.commit()
    assert observation.normalized_features["rainfall_mm_24h"] == 12.0
    assert observation.raw_data["flood_status"] == "NONE"
