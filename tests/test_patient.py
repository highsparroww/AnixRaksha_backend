import pytest

from tests.helpers import auth_headers, register_patient


@pytest.mark.asyncio
async def test_get_and_update_profile(client):
    patient = await register_patient(client, email="profile@test.dev")
    headers = auth_headers(patient["access_token"])

    resp = await client.get("/api/v1/patient/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Test Patient"

    resp = await client.put("/api/v1/patient/me", json={"full_name": "Updated Name", "age": 31}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Updated Name"
    assert resp.json()["data"]["age"] == 31


@pytest.mark.asyncio
async def test_submit_symptoms_returns_prediction(client):
    patient = await register_patient(client, email="symptoms@test.dev")
    headers = auth_headers(patient["access_token"])

    resp = await client.post(
        "/api/v1/patient/symptoms",
        json={
            "symptoms": ["DIARRHEA", "VOMITING", "FEVER"],
            "duration_hours": 48,
            "temperature": 38.2,
            "severity": "MODERATE",
            "notes": "test",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["predicted_disease"] in {
        "CHOLERA", "TYPHOID", "HEPATITIS_A", "HEPATITIS_E", "DYSENTERY", "ROTAVIRUS", "OTHER_WATER_BORNE",
    }
    assert 0 <= data["confidence"] <= 1
    assert data["is_water_borne"] is True
    assert "not a confirmed diagnosis" in data["disclaimer"]
    assert len(data["precautions"]) >= 3
    assert any("water" in item.lower() for item in data["precautions"])


@pytest.mark.asyncio
async def test_prediction_history(client):
    patient = await register_patient(client, email="history@test.dev")
    headers = auth_headers(patient["access_token"])

    for _ in range(3):
        await client.post(
            "/api/v1/patient/symptoms",
            json={"symptoms": ["FEVER"], "severity": "MILD"},
            headers=headers,
        )

    resp = await client.get("/api/v1/patient/predictions", headers=headers)
    assert resp.status_code == 200
    
    assert len(resp.json()["data"]) == 3


@pytest.mark.asyncio
async def test_symptom_suggestions_are_empty_without_local_activity(client):
    patient = await register_patient(client, email="suggestions@test.dev", lat=26.4499, lon=80.3319)

    resp = await client.get("/api/v1/patient/symptom-suggestions", headers=auth_headers(patient["access_token"]))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["suggestions"] == []
    assert "does not diagnose" in data["disclaimer"]


@pytest.mark.asyncio
async def test_dashboard_returns_full_shape(client):
    patient = await register_patient(client, email="dash@test.dev")
    headers = auth_headers(patient["access_token"])

    resp = await client.get("/api/v1/patient/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    for key in [
        "profile", "disease_activity", "rising_diseases", "outbreak_alerts", "map",
        "upcoming_appointments", "unread_notification_count", "notifications",
        "nearby_clinics", "recent_predictions",
    ]:
        assert key in data
