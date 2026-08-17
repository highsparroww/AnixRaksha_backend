from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import auth_headers, register_doctor, register_patient

CLUSTER = (26.47, 80.35)


@pytest.mark.asyncio
async def test_full_end_to_end_demo_scenario(client):
    # 1. Patient registers and logs in
    patient = await register_patient(client, email="e2e-patient@test.dev", lat=CLUSTER[0], lon=CLUSTER[1])
    patient_headers = auth_headers(patient["access_token"])

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "e2e-patient@test.dev", "password": "TestPass123!"}
    )
    assert login_resp.status_code == 200

    # 2. Patient submits symptoms -> mock ML -> prediction stored
    resp = await client.post(
        "/api/v1/patient/symptoms",
        json={
            "symptoms": ["DIARRHEA", "VOMITING", "FEVER", "DEHYDRATION"],
            "duration_hours": 48,
            "temperature": 38.6,
            "severity": "SEVERE",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 201
    prediction = resp.json()["data"]
    assert prediction["confidence"] > 0

    # 3. Doctor registers, creates a slot
    doctor = await register_doctor(client, email="e2e-doctor@test.dev", lat=CLUSTER[0], lon=CLUSTER[1])
    doctor_headers = auth_headers(doctor["access_token"])

    start = datetime.now(timezone.utc) + timedelta(hours=3)
    end = start + timedelta(minutes=15)
    resp = await client.post(
        "/api/v1/doctor/slots",
        json={"start_time": start.isoformat(), "end_time": end.isoformat()},
        headers=doctor_headers,
    )
    slot = resp.json()["data"]

    # 4. Patient books appointment
    resp = await client.post(
        "/api/v1/patient/appointments",
        json={"doctor_id": slot["doctor_id"], "slot_id": slot["id"], "reason": "Severe diarrhea and fever"},
        headers=patient_headers,
    )
    assert resp.status_code == 201
    appointment = resp.json()["data"]

    # 5. Doctor opens appointment and sees pre-test information
    resp = await client.get(f"/api/v1/doctor/appointments/{appointment['id']}", headers=doctor_headers)
    assert resp.status_code == 200
    detail = resp.json()["data"]
    assert detail["prediction"]["predicted_disease"] == prediction["predicted_disease"]
    assert detail["severity"] == "SEVERE"

    # 6. Doctor creates a CONFIRMED case for the registered patient
    resp = await client.post(
        "/api/v1/doctor/cases",
        json={
            "disease": "CHOLERA",
            "case_status": "CONFIRMED",
            "patient_id": detail["patient_id"],
            "age": 28,
            "gender": "MALE",
            "latitude": CLUSTER[0],
            "longitude": CLUSTER[1],
            "notes": "Confirmed cholera after clinical exam",
        },
        headers=doctor_headers,
    )
    assert resp.status_code == 201

    # 7. Surveillance updated: case count increases
    resp = await client.get(
        "/api/v1/surveillance/activity",
        params={"latitude": CLUSTER[0], "longitude": CLUSTER[1], "radius_km": 10},
        headers=patient_headers,
    )
    assert resp.json()["data"]["total_cases"] == 1

    # 8. Unregistered patient case created by the same doctor
    resp = await client.post(
        "/api/v1/doctor/cases",
        json={
            "disease": "CHOLERA",
            "case_status": "CONFIRMED",
            "age": 60,
            "gender": "FEMALE",
            "latitude": CLUSTER[0] + 0.001,
            "longitude": CLUSTER[1] + 0.001,
            "notes": "Unregistered walk-in patient",
        },
        headers=doctor_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["patient_id"] is None

    resp = await client.get(
        "/api/v1/surveillance/activity",
        params={"latitude": CLUSTER[0], "longitude": CLUSTER[1], "radius_km": 10},
        headers=patient_headers,
    )
    assert resp.json()["data"]["total_cases"] == 2

    # 9. More clustered cases pushed in via the dev simulator to cross the outbreak threshold
    resp = await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "CHOLERA",
            "latitude": CLUSTER[0],
            "longitude": CLUSTER[1],
            "radius_km": 5,
            "number_of_cases": 20,
            "hours": 24,
        },
    )
    assert resp.status_code == 201

    # 10. Outbreak alert now exists
    resp = await client.get(
        "/api/v1/surveillance/outbreaks",
        params={"latitude": CLUSTER[0], "longitude": CLUSTER[1]},
        headers=patient_headers,
    )
    alerts = resp.json()["data"]
    assert len(alerts) >= 1
    assert alerts[0]["disease"] == "CHOLERA"

    # 11. Registered patient within radius received a notification
    resp = await client.get("/api/v1/notifications", headers=patient_headers)
    notifications = resp.json()["data"]
    assert any(n["type"] == "OUTBREAK_ALERT" for n in notifications)

    # 12. Patient dashboard reflects elevated/critical activity + alerts + prevention guidance
    resp = await client.get("/api/v1/patient/dashboard", headers=patient_headers)
    dashboard = resp.json()["data"]
    assert dashboard["disease_activity"]["activity_level"] in {"WATCH", "ELEVATED", "HIGH", "CRITICAL"}
    assert len(dashboard["outbreak_alerts"]) >= 1
    assert len(dashboard["outbreak_alerts"][0]["prevention_guidance"]) > 0

    # 13. Patient can find nearby clinics (empty is fine here, endpoint just must work)
    resp = await client.get("/api/v1/patient/nearby-clinics", headers=patient_headers)
    assert resp.status_code == 200
