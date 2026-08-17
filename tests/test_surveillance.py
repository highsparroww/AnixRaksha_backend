import pytest

from tests.helpers import auth_headers, register_doctor, register_patient

CENTER = (26.4499, 80.3319)


async def _create_case(client, headers, disease="CHOLERA", status="CONFIRMED", lat=None, lon=None):
    lat = lat if lat is not None else CENTER[0]
    lon = lon if lon is not None else CENTER[1]
    resp = await client.post(
        "/api/v1/doctor/cases",
        json={"disease": disease, "case_status": status, "age": 30, "gender": "MALE", "latitude": lat, "longitude": lon},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_nearby_surveillance_is_aggregated_and_uses_postgis_radius(client):
    doctor = await register_doctor(client, email="geo-doc@test.dev")
    headers = auth_headers(doctor["access_token"])

    # a case right at the center
    await _create_case(client, headers, lat=CENTER[0], lon=CENTER[1])
    # a case far away (~100km+), should be excluded from a 10km search
    await _create_case(client, headers, lat=CENTER[0] + 1.0, lon=CENTER[1] + 1.0)

    resp = await client.get(
        "/api/v1/surveillance/nearby",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_cases"] == 1
    assert data["cases_by_disease"] == {"CHOLERA": 1}
    # No row-level data or quasi-identifiers may cross the patient-facing API.
    forbidden = {"patient_id", "doctor_id", "age", "gender", "latitude", "longitude", "id", "cases"}
    assert not (forbidden & set(data))


@pytest.mark.asyncio
async def test_disease_activity_counts_and_status_breakdown(client):
    doctor = await register_doctor(client, email="activity-doc@test.dev")
    headers = auth_headers(doctor["access_token"])

    await _create_case(client, headers, disease="CHOLERA", status="CONFIRMED")
    await _create_case(client, headers, disease="CHOLERA", status="SUSPECTED")
    await _create_case(client, headers, disease="TYPHOID", status="PROBABLE")

    resp = await client.get(
        "/api/v1/surveillance/activity",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_cases"] == 3
    assert data["cases_by_disease"]["CHOLERA"] == 2
    assert data["cases_by_disease"]["TYPHOID"] == 1
    assert data["confirmed"] == 1
    assert data["suspected"] == 1
    assert data["probable"] == 1
    assert data["cases_last_24h"] == 3
    assert data["cases_last_7d"] == 3


@pytest.mark.asyncio
async def test_map_aggregation_never_exposes_exact_case_location_fields(client):
    doctor = await register_doctor(client, email="map-doc@test.dev")
    headers = auth_headers(doctor["access_token"])
    await _create_case(client, headers)

    resp = await client.get(
        "/api/v1/surveillance/map",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    cells = resp.json()["data"]["cells"]
    assert len(cells) >= 1
    for cell in cells:
        assert set(cell.keys()) == {"cell_id", "latitude", "longitude", "case_count", "diseases", "activity_level"}
        assert cell["activity_level"] in {"NORMAL", "WATCH", "ELEVATED", "HIGH", "CRITICAL"}


@pytest.mark.asyncio
async def test_simulate_outbreak_triggers_alert(client):
    resp = await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "CHOLERA",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "radius_km": 5,
            "number_of_cases": 20,
            "hours": 24,
        },
    )
    assert resp.status_code == 201
    assert len(resp.json()["data"]) == 20

    patient = await register_patient(client, email="outbreak-check@test.dev", lat=CENTER[0], lon=CENTER[1])
    resp = await client.get(
        "/api/v1/surveillance/outbreaks",
        params={"latitude": CENTER[0], "longitude": CENTER[1]},
        headers=auth_headers(patient["access_token"]),
    )
    assert resp.status_code == 200
    alerts = resp.json()["data"]
    assert len(alerts) >= 1
    assert alerts[0]["disease"] == "CHOLERA"
    assert alerts[0]["severity"] in {"WATCH", "ELEVATED", "HIGH", "CRITICAL"}
    assert len(alerts[0]["prevention_guidance"]) > 0


@pytest.mark.asyncio
async def test_registered_patient_within_radius_receives_notification_on_outbreak(client):
    patient = await register_patient(client, email="notif-target@test.dev", lat=CENTER[0], lon=CENTER[1])

    resp = await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "DYSENTERY",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "radius_km": 5,
            "number_of_cases": 20,
            "hours": 24,
        },
    )
    assert resp.status_code == 201

    resp = await client.get("/api/v1/notifications", headers=auth_headers(patient["access_token"]))
    assert resp.status_code == 200
    notifications = resp.json()["data"]
    assert any(n["type"] == "OUTBREAK_ALERT" for n in notifications)
