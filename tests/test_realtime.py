"""Realtime WebSocket tests.

These use `ws_app_client`, a plain async context manager (see conftest.py)
rather than a pytest fixture, so that the WebSocket-capable ASGI transport's
internal task/cancel-scope lifecycle stays within a single test task.

The full bidirectional realtime pipeline (case created -> surveillance
updated -> outbreak detected -> notification -> WebSocket push, and
appointment booked -> WebSocket push to doctor) is also verified against a
live running server via ws_smoke_test.py at the project root, which exercises
real OS sockets end-to-end.
"""
import pytest

from tests.conftest import ws_app_client
from tests.helpers import auth_headers, register_doctor, register_patient


@pytest.mark.asyncio
async def test_websocket_connects_with_valid_token():
    from httpx_ws import aconnect_ws

    async with ws_app_client() as client:
        patient = await register_patient(client, email="ws-conn@test.dev")
        token = patient["access_token"]

        async with aconnect_ws(f"ws://test/ws?token={token}", client=client) as ws:
            assert ws is not None


@pytest.mark.asyncio
async def test_websocket_rejects_missing_token():
    from httpx_ws import aconnect_ws, WebSocketDisconnect

    async with ws_app_client() as client:
        with pytest.raises(WebSocketDisconnect):
            async with aconnect_ws("ws://test/ws", client=client):
                pass


@pytest.mark.asyncio
async def test_appointment_booking_triggers_realtime_event_to_doctor():
    from httpx_ws import aconnect_ws
    from datetime import datetime, timedelta, timezone

    async with ws_app_client() as client:
        doctor = await register_doctor(client, email="ws-doc@test.dev")
        doctor_headers = auth_headers(doctor["access_token"])

        start = datetime.now(timezone.utc) + timedelta(hours=5)
        end = start + timedelta(minutes=15)
        resp = await client.post(
            "/api/v1/doctor/slots",
            json={"start_time": start.isoformat(), "end_time": end.isoformat()},
            headers=doctor_headers,
        )
        slot = resp.json()["data"]

        patient = await register_patient(client, email="ws-patient@test.dev")

        received_types = []
        async with aconnect_ws(f"ws://test/ws?token={doctor['access_token']}", client=client) as ws:
            await client.post(
                "/api/v1/patient/appointments",
                json={"doctor_id": slot["doctor_id"], "slot_id": slot["id"], "reason": "test"},
                headers=auth_headers(patient["access_token"]),
            )
            # The doctor receives both a NOTIFICATION and an APPOINTMENT_BOOKED
            # event for a single booking; check both arrive without requiring
            # a specific order.
            for _ in range(2):
                message = await ws.receive_json(timeout=5)
                received_types.append(message["type"])

        assert "APPOINTMENT_BOOKED" in received_types
        assert "NOTIFICATION" in received_types


@pytest.mark.asyncio
async def test_case_creation_triggers_surveillance_updated_event():
    from httpx_ws import aconnect_ws

    async with ws_app_client() as client:
        doctor = await register_doctor(client, email="ws-case-doc@test.dev")
        headers = auth_headers(doctor["access_token"])

        async with aconnect_ws(f"ws://test/ws?token={doctor['access_token']}", client=client) as ws:
            response = await client.post(
                "/api/v1/doctor/cases",
                json={
                    "disease": "CHOLERA",
                    "case_status": "CONFIRMED",
                    "latitude": 26.4499,
                    "longitude": 80.3319,
                },
                headers=headers,
            )
            assert response.status_code == 201
            received_types = {(await ws.receive_json(timeout=5))["type"] for _ in range(2)}

        assert "SURVEILLANCE_UPDATED" in received_types
