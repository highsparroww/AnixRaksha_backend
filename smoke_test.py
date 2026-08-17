"""Manual smoke test: exercises the full WaterWatch demo scenario against a
running server (python3 smoke_test.py). Not part of pytest suite."""
import asyncio
import json

import httpx

BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        def show(label, resp):
            print(f"\n=== {label} [{resp.status_code}] ===")
            try:
                print(json.dumps(resp.json(), indent=2)[:1500])
            except Exception:
                print(resp.text[:500])

        # Patient login
        r = await client.post("/api/v1/auth/login", json={"email": "patient1@waterwatch.dev", "password": "Patient123!"})
        show("patient login", r)
        patient_token = r.json()["data"]["access_token"]
        p_headers = {"Authorization": f"Bearer {patient_token}"}

        # Doctor login
        r = await client.post("/api/v1/auth/login", json={"email": "doctor2@waterwatch.dev", "password": "Doctor123!"})
        show("doctor login", r)
        doctor_token = r.json()["data"]["access_token"]
        d_headers = {"Authorization": f"Bearer {doctor_token}"}

        # Doctor profile + dashboard
        r = await client.get("/api/v1/doctor/me", headers=d_headers)
        show("doctor profile", r)

        r = await client.get("/api/v1/doctor/dashboard", headers=d_headers)
        show("doctor dashboard", r)

        # Doctor creates a slot
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
        end = start + timedelta(minutes=15)
        r = await client.post(
            "/api/v1/doctor/slots",
            headers=d_headers,
            json={"start_time": start.isoformat(), "end_time": end.isoformat()},
        )
        show("doctor create slot", r)
        slot_id = r.json()["data"]["id"]
        doctor_id = r.json()["data"]["doctor_id"]

        # Patient books the slot
        r = await client.post(
            "/api/v1/patient/appointments",
            headers=p_headers,
            json={"doctor_id": doctor_id, "slot_id": slot_id, "reason": "Diarrhea and fever for 2 days"},
        )
        show("patient books appointment", r)
        appointment_id = r.json()["data"]["id"]

        # Double-booking should fail with 409
        r = await client.post(
            "/api/v1/patient/appointments",
            headers=p_headers,
            json={"doctor_id": doctor_id, "slot_id": slot_id, "reason": "duplicate attempt"},
        )
        show("duplicate booking (expect 409)", r)
        assert r.status_code == 409

        # Doctor opens appointment detail (pre-test info)
        r = await client.get(f"/api/v1/doctor/appointments/{appointment_id}", headers=d_headers)
        show("doctor appointment detail", r)

        # Doctor registers a CONFIRMED case for this patient
        patient_id = r.json()["data"]["patient_id"]
        r = await client.post(
            "/api/v1/doctor/cases",
            headers=d_headers,
            json={
                "disease": "CHOLERA",
                "case_status": "CONFIRMED",
                "patient_id": patient_id,
                "age": 30,
                "gender": "MALE",
                "latitude": 26.47,
                "longitude": 80.35,
                "notes": "Confirmed after examination",
            },
        )
        show("doctor registers confirmed case", r)

        # Unregistered patient case
        r = await client.post(
            "/api/v1/doctor/cases",
            headers=d_headers,
            json={
                "disease": "CHOLERA",
                "case_status": "CONFIRMED",
                "age": 45,
                "gender": "FEMALE",
                "latitude": 26.471,
                "longitude": 80.351,
                "notes": "Walk-in unregistered patient",
            },
        )
        show("unregistered patient case", r)
        assert r.json()["data"]["patient_id"] is None

        # Surveillance nearby / activity / map around the cluster
        r = await client.get(
            "/api/v1/surveillance/activity", headers=p_headers, params={"latitude": 26.47, "longitude": 80.35, "radius_km": 10}
        )
        show("surveillance activity (cluster)", r)

        r = await client.get(
            "/api/v1/surveillance/map", headers=p_headers, params={"latitude": 26.47, "longitude": 80.35, "radius_km": 10}
        )
        show("surveillance map (cluster)", r)

        # Trigger outbreak via simulate-outbreak
        r = await client.post(
            "/api/v1/dev/simulate-outbreak",
            json={
                "disease": "CHOLERA",
                "latitude": 26.47,
                "longitude": 80.35,
                "radius_km": 5,
                "number_of_cases": 20,
                "hours": 24,
            },
        )
        print(f"\n=== simulate-outbreak [{r.status_code}] === created {len(r.json().get('data', []))} cases")

        # Check outbreak alerts
        r = await client.get("/api/v1/surveillance/outbreaks", headers=p_headers, params={"latitude": 26.47, "longitude": 80.35})
        show("outbreak alerts", r)

        # Patient dashboard should now show elevated activity + alerts + notifications
        r = await client.get("/api/v1/patient/dashboard", headers=p_headers)
        data = r.json()["data"]
        print(f"\n=== patient dashboard after outbreak [{r.status_code}] ===")
        print("activity_level:", data["disease_activity"]["activity_level"])
        print("outbreak_alerts:", len(data["outbreak_alerts"]))
        print("unread_notifications:", data["unread_notification_count"])

        # Notifications list + mark read
        r = await client.get("/api/v1/notifications", headers=p_headers)
        notifications = r.json()["data"]
        print(f"\n=== notifications [{r.status_code}] === count={len(notifications)}")
        if notifications:
            nid = notifications[0]["id"]
            r = await client.patch(f"/api/v1/notifications/{nid}/read", headers=p_headers)
            print(f"mark read [{r.status_code}]")

        # Clinics nearby
        r = await client.get("/api/v1/clinics/nearby", headers=p_headers, params={"latitude": 26.47, "longitude": 80.35, "radius_km": 15})
        show("clinics nearby", r)

        print("\n\nEND-TO-END SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
