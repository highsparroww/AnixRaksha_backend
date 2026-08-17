import random

from fastapi import APIRouter, Depends, status

from app.config import settings
from app.database import get_db
from app.dependencies import AppError
from app.models.enums import CaseSource, CaseStatus
from app.schemas.schemas import DiseaseCaseResponse, Envelope, SimulateCaseRequest, SimulateOutbreakRequest
from app.services.case import create_disease_case
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


def _require_dev_mode() -> None:
    if settings.APP_ENV != "development":
        raise AppError(status.HTTP_403_FORBIDDEN, "DEV_MODE_DISABLED", "Development endpoints are disabled")


@router.post("/simulate-case", response_model=Envelope[DiseaseCaseResponse], status_code=status.HTTP_201_CREATED)
async def simulate_case(payload: SimulateCaseRequest, db: AsyncSession = Depends(get_db)):
    _require_dev_mode()
    case = await create_disease_case(
        db,
        disease=payload.disease.value,
        case_status=payload.case_status.value,
        source=CaseSource.IMPORTED.value,
        latitude=payload.latitude,
        longitude=payload.longitude,
        age=payload.age,
        gender=payload.gender.value if payload.gender else None,
        notes="Simulated case (dev)",
    )
    await db.commit()
    await db.refresh(case)
    return Envelope(data=DiseaseCaseResponse.model_validate(case))


@router.post("/simulate-outbreak", response_model=Envelope[list[DiseaseCaseResponse]], status_code=status.HTTP_201_CREATED)
async def simulate_outbreak(payload: SimulateOutbreakRequest, db: AsyncSession = Depends(get_db)):
    """Create a cluster of cases scattered around a center point over the
    given time window, to trigger rising-case / outbreak detection."""
    _require_dev_mode()

    created = []
    for i in range(payload.number_of_cases):
        # scatter points within radius_km using a simple random offset in degrees
        offset_km = random.uniform(0, payload.radius_km)
        angle = random.uniform(0, 6.28318)
        # ~111 km per degree latitude
        d_lat = (offset_km / 111.0) * random.uniform(-1, 1)
        d_lon = (offset_km / 111.0) * random.uniform(-1, 1)
        lat = payload.latitude + d_lat
        lon = payload.longitude + d_lon

        hours_ago = random.uniform(0, payload.hours)
        from datetime import datetime, timedelta, timezone

        reported_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

        case = await create_disease_case(
            db,
            disease=payload.disease.value,
            case_status=CaseStatus.CONFIRMED.value,
            source=CaseSource.IMPORTED.value,
            latitude=lat,
            longitude=lon,
            age=random.randint(5, 70),
            gender=random.choice(["MALE", "FEMALE", "OTHER"]),
            notes="Simulated outbreak case (dev)",
            reported_at=reported_at,
        )
        created.append(case)

    await db.commit()
    for c in created:
        await db.refresh(c)
    return Envelope(data=[DiseaseCaseResponse.model_validate(c) for c in created])
