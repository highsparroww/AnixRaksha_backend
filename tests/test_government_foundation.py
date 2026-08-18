import pytest

from tests.helpers import auth_headers


async def register_government(client):
    response = await client.post("/api/v1/auth/register", json={
        "role": "GOVERNMENT", "full_name": "Government Reviewer",
        "email": "government@test.dev", "password": "TestPass123!",
    })
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_government_can_collect_aggregate_signal_but_patient_cannot(client):
    government = await register_government(client)
    response = await client.post("/api/v1/government/signals", json={
        "signal_type": "WASTEWATER", "source": "ward-lab", "latitude": 26.45,
        "longitude": 80.33, "observed_at": "2026-08-18T00:00:00Z",
        "disease": "CHOLERA", "data": {"positive_samples": 3},
    }, headers=auth_headers(government["access_token"]))
    assert response.status_code == 201
    assert response.json()["data"]["signal_type"] == "WASTEWATER"
