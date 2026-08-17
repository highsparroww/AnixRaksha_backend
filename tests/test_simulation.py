import pytest

CENTER = (26.4499, 80.3319)


@pytest.mark.asyncio
async def test_simulate_case(client):
    resp = await client.post(
        "/api/v1/dev/simulate-case",
        json={
            "disease": "CHOLERA",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "case_status": "CONFIRMED",
            "age": 30,
            "gender": "MALE",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["disease"] == "CHOLERA"
    assert data["patient_id"] is None


@pytest.mark.asyncio
async def test_simulate_outbreak_creates_scattered_cases(client):
    resp = await client.post(
        "/api/v1/dev/simulate-outbreak",
        json={
            "disease": "TYPHOID",
            "latitude": CENTER[0],
            "longitude": CENTER[1],
            "radius_km": 8,
            "number_of_cases": 15,
            "hours": 48,
        },
    )
    assert resp.status_code == 201
    cases = resp.json()["data"]
    assert len(cases) == 15
    for case in cases:
        assert case["disease"] == "TYPHOID"
        assert case["case_status"] == "CONFIRMED"
