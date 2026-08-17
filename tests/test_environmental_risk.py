from datetime import datetime, timezone

import pytest

from app.main import app
from tests.helpers import auth_headers, register_patient


@pytest.mark.asyncio
async def test_environmental_risk_uses_mock_without_claiming_live_data(client):
    patient = await register_patient(client, email="environment@test.dev", lat=26.45, lon=80.33)
    response = await client.get("/api/v1/environmental-risk/me", headers=auth_headers(patient["access_token"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["risk_level"] == "NORMAL"
    assert data["data_status"] == "NO_LIVE_ENVIRONMENTAL_DATA"
    assert "not a disease diagnosis" in data["disclaimer"]


@pytest.mark.asyncio
async def test_elevated_environmental_risk_creates_a_realtime_notification(client):
    patient = await register_patient(client, email="environment-alert@test.dev", lat=26.45, lon=80.33)

    class ElevatedRiskService:
        async def assess(self, latitude, longitude):
            return {
                "risk_level": "ELEVATED",
                "risk_score": 0.72,
                "potential_water_borne_diseases": ["CHOLERA", "TYPHOID"],
                "potential_vector_borne_diseases": ["MALARIA"],
                "contributing_factors": [
                    {"factor": "FLOODING", "severity": "HIGH", "reason": "Recent local flooding."},
                    {"factor": "OPEN_SEWAGE", "severity": "ELEVATED", "reason": "Reported sanitation hazard."},
                ],
                "prevention_guidance": ["Use safe water.", "Avoid standing water and use mosquito protection."],
                "data_status": "LIVE_ENVIRONMENTAL_MODEL",
                "assessed_at": datetime.now(timezone.utc),
            }

    original_service = app.state.environmental_risk_registry._service
    app.state.environmental_risk_registry._service = ElevatedRiskService()
    try:
        response = await client.get("/api/v1/environmental-risk/me", headers=auth_headers(patient["access_token"]))
        assert response.status_code == 200
    finally:
        app.state.environmental_risk_registry._service = original_service

    notifications = await client.get("/api/v1/notifications", headers=auth_headers(patient["access_token"]))
    assert any(item["type"] == "ENVIRONMENTAL_RISK" for item in notifications.json()["data"])
