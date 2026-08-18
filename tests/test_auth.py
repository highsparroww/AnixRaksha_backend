import pytest

from tests.helpers import auth_headers, register_doctor, register_patient


@pytest.mark.asyncio
async def test_register_patient(client):
    data = await register_patient(client, email="alice@test.dev")
    assert data["role"] == "PATIENT"
    assert data["access_token"]


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client):
    await register_patient(client, email="dup@test.dev")
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "role": "PATIENT",
            "full_name": "Another",
            "email": "dup@test.dev",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.asyncio
async def test_login_success(client):
    await register_patient(client, email="bob@test.dev")
    resp = await client.post("/api/v1/auth/login", json={"email": "bob@test.dev", "password": "TestPass123!"})
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_login_invalid_password(client):
    await register_patient(client, email="carl@test.dev")
    resp = await client.post("/api/v1/auth/login", json={"email": "carl@test.dev", "password": "WrongPass!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_jwt_required_for_protected_route(client):
    resp = await client.get("/api/v1/patient/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rbac_patient_cannot_access_doctor_routes(client):
    patient = await register_patient(client, email="rbac-patient@test.dev")
    resp = await client.get("/api/v1/doctor/me", headers=auth_headers(patient["access_token"]))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rbac_doctor_cannot_access_patient_routes(client):
    doctor = await register_doctor(client, email="rbac-doctor@test.dev")
    resp = await client.get("/api/v1/patient/me", headers=auth_headers(doctor["access_token"]))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_rotates_and_logout_revokes_session(client):
    registered = await register_patient(client, email="refresh@test.dev")
    first = await client.post("/api/v1/auth/refresh")
    assert first.status_code == 200, first.text
    assert first.json()["data"]["access_token"]

    # The client now holds the rotated cookie. Logging out revokes that session.
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    expired = await client.post("/api/v1/auth/refresh")
    assert expired.status_code == 401
