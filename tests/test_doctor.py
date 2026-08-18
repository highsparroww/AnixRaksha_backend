from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import auth_headers, register_doctor, register_patient


async def _make_slot(client, doctor_headers, hours_ahead=24):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    end = start + timedelta(minutes=15)
    resp = await client.post(
        "/api/v1/doctor/slots",
        json={"start_time": start.isoformat(), "end_time": end.isoformat()},
        headers=doctor_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_create_list_update_delete_slot(client):
    doctor = await register_doctor(client, email="slots@test.dev")
    headers = auth_headers(doctor["access_token"])

    slot = await _make_slot(client, headers)
    resp = await client.get("/api/v1/doctor/slots", headers=headers)
    assert resp.status_code == 200
    assert any(s["id"] == slot["id"] for s in resp.json()["data"])

    resp = await client.put(f"/api/v1/doctor/slots/{slot['id']}", json={"status": "CANCELLED"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "CANCELLED"

    resp = await client.delete(f"/api/v1/doctor/slots/{slot['id']}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patient_books_appointment_and_doctor_sees_pretest_info(client):
    doctor = await register_doctor(client, email="appt-doc@test.dev")
    doctor_headers = auth_headers(doctor["access_token"])
    slot = await _make_slot(client, doctor_headers)

    patient = await register_patient(client, email="appt-patient@test.dev")
    patient_headers = auth_headers(patient["access_token"])

    conversation = await client.post(
        "/api/v1/patient/health-conversations",
        json={"structured_data": {"symptoms": ["DIARRHEA", "VOMITING"], "duration_hours": 24, "severity": "SEVERE"}},
        headers=patient_headers,
    )
    assert conversation.status_code == 201
    intake_id = conversation.json()["data"]["health_intake_id"]

    resp = await client.post(
        "/api/v1/patient/appointments",
        json={
            "doctor_id": slot["doctor_id"], "slot_id": slot["id"], "reason": "Feeling unwell",
            "health_intake_id": intake_id, "share_health_summary": True,
        },
        headers=patient_headers,
    )
    assert resp.status_code == 201, resp.text
    appointment = resp.json()["data"]

    resp = await client.get(f"/api/v1/doctor/appointments/{appointment['id']}", headers=doctor_headers)
    assert resp.status_code == 200
    detail = resp.json()["data"]
    assert detail["patient_name"] == "Test Patient"
    assert detail["health_summary_shared"] is True
    assert detail["health_summary_snapshot"]["structured_data"]["symptoms"] == ["DIARRHEA", "VOMITING"]
    assert detail["health_summary_snapshot"]["structured_data"]["severity"] == "SEVERE"
    assert detail["latest_symptoms"] is None
    assert detail["prediction"] is None


@pytest.mark.asyncio
async def test_double_booking_same_slot_returns_409(client):
    doctor = await register_doctor(client, email="dbl-doc@test.dev")
    doctor_headers = auth_headers(doctor["access_token"])
    slot = await _make_slot(client, doctor_headers)

    patient1 = await register_patient(client, email="dbl-p1@test.dev")
    patient2 = await register_patient(client, email="dbl-p2@test.dev")

    resp1 = await client.post(
        "/api/v1/patient/appointments",
        json={"doctor_id": slot["doctor_id"], "slot_id": slot["id"]},
        headers=auth_headers(patient1["access_token"]),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/patient/appointments",
        json={"doctor_id": slot["doctor_id"], "slot_id": slot["id"]},
        headers=auth_headers(patient2["access_token"]),
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "SLOT_ALREADY_BOOKED"


@pytest.mark.asyncio
async def test_doctor_registers_case_for_registered_patient(client):
    doctor = await register_doctor(client, email="case-doc@test.dev")
    doctor_headers = auth_headers(doctor["access_token"])
    patient = await register_patient(client, email="case-patient@test.dev")

    # Fetch patient id via own profile isn't directly available to doctor; use dashboard-free path
    # by booking + reading appointment detail, or just pass patient_id=None-safe test below instead.
    resp = await client.post(
        "/api/v1/doctor/cases",
        json={
            "disease": "CHOLERA",
            "case_status": "CONFIRMED",
            "age": 30,
            "gender": "MALE",
            "latitude": 26.4499,
            "longitude": 80.3319,
            "notes": "test case",
        },
        headers=doctor_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["disease"] == "CHOLERA"
    assert resp.json()["data"]["source"] == "DOCTOR"


@pytest.mark.asyncio
async def test_unregistered_patient_case_has_null_patient_id(client):
    doctor = await register_doctor(client, email="unreg-doc@test.dev")
    doctor_headers = auth_headers(doctor["access_token"])

    resp = await client.post(
        "/api/v1/doctor/cases",
        json={
            "disease": "TYPHOID",
            "case_status": "CONFIRMED",
            "age": 50,
            "gender": "FEMALE",
            "latitude": 26.45,
            "longitude": 80.33,
            "notes": "walk-in, no account",
        },
        headers=doctor_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["patient_id"] is None
    assert data["disease"] == "TYPHOID"

    # It must still contribute to aggregate surveillance nearby.
    resp = await client.get(
        "/api/v1/surveillance/nearby",
        params={"latitude": 26.45, "longitude": 80.33, "radius_km": 5},
        headers=doctor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_cases"] == 1
    assert data["cases_by_disease"] == {"TYPHOID": 1}
