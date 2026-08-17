import pytest
from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select

from app.models.models import Clinic
from app.services.geo import make_point
from tests.helpers import auth_headers, register_patient

CENTER = (26.4499, 80.3319)


async def _seed_clinics(db_session):
    clinics = [
        Clinic(
            name="Gov Clinic A", type="GOVERNMENT", address="A", phone="1",
            location=make_point(CENTER[0] + 0.01, CENTER[1] + 0.01),
            latitude=CENTER[0] + 0.01, longitude=CENTER[1] + 0.01,
            opening_time="08:00", closing_time="20:00",
        ),
        Clinic(
            name="Private Clinic B", type="PRIVATE", address="B", phone="2",
            location=make_point(CENTER[0] - 0.01, CENTER[1] - 0.01),
            latitude=CENTER[0] - 0.01, longitude=CENTER[1] - 0.01,
            opening_time="09:00", closing_time="18:00",
        ),
        Clinic(
            name="Far Away Clinic", type="GOVERNMENT", address="C", phone="3",
            location=make_point(CENTER[0] + 2.0, CENTER[1] + 2.0),
            latitude=CENTER[0] + 2.0, longitude=CENTER[1] + 2.0,
            opening_time="08:00", closing_time="20:00",
        ),
    ]
    for c in clinics:
        db_session.add(c)
    await db_session.commit()


@pytest.mark.asyncio
async def test_nearby_clinics_sorted_by_distance(client, db_session):
    await _seed_clinics(db_session)
    patient = await register_patient(client, email="clinic-p@test.dev")

    resp = await client.get(
        "/api/v1/clinics/nearby",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 5},
        headers=auth_headers(patient["access_token"]),
    )
    assert resp.status_code == 200
    clinics = resp.json()["data"]
    assert len(clinics) == 2  # far away one excluded
    distances = [c["distance_km"] for c in clinics]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_nearby_clinics_filter_by_type(client, db_session):
    await _seed_clinics(db_session)
    patient = await register_patient(client, email="clinic-p2@test.dev")

    resp = await client.get(
        "/api/v1/clinics/nearby",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 5, "type": "GOVERNMENT"},
        headers=auth_headers(patient["access_token"]),
    )
    assert resp.status_code == 200
    clinics = resp.json()["data"]
    assert all(c["type"] == "GOVERNMENT" for c in clinics)
    assert len(clinics) == 1

    resp = await client.get(
        "/api/v1/clinics/nearby",
        params={"latitude": CENTER[0], "longitude": CENTER[1], "radius_km": 5, "type": "PRIVATE"},
        headers=auth_headers(patient["access_token"]),
    )
    clinics = resp.json()["data"]
    assert all(c["type"] == "PRIVATE" for c in clinics)
    assert len(clinics) == 1
