import pytest

from tests.helpers import auth_headers, register_patient

CENTER = (26.4499, 80.3319)


@pytest.mark.asyncio
async def test_notifications_created_and_mark_read(client):
    patient = await register_patient(client, email="notif-p@test.dev", lat=CENTER[0], lon=CENTER[1])
    headers = auth_headers(patient["access_token"])

    await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "ROTAVIRUS",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "radius_km": 5,
            "number_of_cases": 20,
            "hours": 24,
        },
    )

    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    notifications = resp.json()["data"]
    assert len(notifications) >= 1
    assert all(not n["is_read"] for n in notifications)

    nid = notifications[0]["id"]
    resp = await client.patch(f"/api/v1/notifications/{nid}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["is_read"] is True

    resp = await client.patch("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/notifications", headers=headers)
    assert all(n["is_read"] for n in resp.json()["data"])


@pytest.mark.asyncio
async def test_cannot_read_another_users_notification(client):
    patient1 = await register_patient(client, email="notif-owner@test.dev", lat=CENTER[0], lon=CENTER[1])
    patient2 = await register_patient(client, email="notif-other@test.dev")

    await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "HEPATITIS_A",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "radius_km": 5,
            "number_of_cases": 20,
            "hours": 24,
        },
    )

    resp = await client.get("/api/v1/notifications", headers=auth_headers(patient1["access_token"]))
    notifications = resp.json()["data"]
    assert len(notifications) >= 1
    nid = notifications[0]["id"]

    resp = await client.patch(f"/api/v1/notifications/{nid}/read", headers=auth_headers(patient2["access_token"]))
    assert resp.status_code == 404
