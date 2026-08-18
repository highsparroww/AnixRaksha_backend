import pytest

from tests.helpers import auth_headers, register_doctor, register_patient


@pytest.mark.asyncio
async def test_patient_health_intake_is_private_and_archivable(client):
    patient = await register_patient(client, email="conversation-owner@test.dev")
    other = await register_patient(client, email="conversation-other@test.dev")
    headers = auth_headers(patient["access_token"])

    created = await client.post("/api/v1/patient/health-conversations", json={}, headers=headers)
    assert created.status_code == 201, created.text
    conversation_id = created.json()["data"]["id"]

    intake = await client.patch(
        f"/api/v1/patient/health-conversations/{conversation_id}/intake",
        json={"structured_data": {"symptoms": ["FEVER", "VOMITING"], "duration_hours": 24}}, headers=headers,
    )
    assert intake.status_code == 200

    own = await client.get(f"/api/v1/patient/health-conversations/{conversation_id}", headers=headers)
    assert own.status_code == 200
    assert own.json()["data"]["health_intake"]["symptoms"] == ["FEVER", "VOMITING"]

    forbidden = await client.get(
        f"/api/v1/patient/health-conversations/{conversation_id}", headers=auth_headers(other["access_token"])
    )
    assert forbidden.status_code == 404

    archived = await client.post(f"/api/v1/patient/health-conversations/{conversation_id}/archive", headers=headers)
    assert archived.status_code == 200
    blocked = await client.patch(
        f"/api/v1/patient/health-conversations/{conversation_id}/intake",
        json={"structured_data": {"severity": "MILD"}}, headers=headers,
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_doctor_cannot_use_patient_conversation_routes(client):
    doctor = await register_doctor(client, email="conversation-doctor@test.dev")
    response = await client.get("/api/v1/patient/health-conversations", headers=auth_headers(doctor["access_token"]))
    assert response.status_code == 403
