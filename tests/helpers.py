from datetime import datetime, timedelta, timezone

CITY = (26.4499, 80.3319)


async def register_patient(client, email="patient@test.dev", lat=CITY[0], lon=CITY[1]):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "role": "PATIENT",
            "full_name": "Test Patient",
            "email": email,
            "password": "TestPass123!",
            "age": 28,
            "gender": "MALE",
            "phone": "+911234567890",
            "latitude": lat,
            "longitude": lon,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def register_doctor(client, email="doctor@test.dev", lat=CITY[0], lon=CITY[1]):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "role": "DOCTOR",
            "full_name": "Test Doctor",
            "email": email,
            "password": "TestPass123!",
            "phone": "+911234567891",
            "specialization": "General",
            "license_number": "LIC-TEST",
            "latitude": lat,
            "longitude": lon,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
