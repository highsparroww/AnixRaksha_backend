from typing import Optional

from fastapi import APIRouter, Depends, Query
from geoalchemy2.functions import ST_DWithin, ST_Distance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.enums import ClinicType
from app.models.models import Clinic
from app.schemas.schemas import ClinicResponse, Envelope
from app.services.geo import make_point

router = APIRouter(prefix="/api/v1/clinics", tags=["clinics"])


@router.get("/nearby", response_model=Envelope[list[ClinicResponse]])
async def nearby_clinics(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_km: float = Query(10.0, gt=0, le=200),
    type: Optional[ClinicType] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    center = make_point(latitude, longitude)
    distance = ST_Distance(Clinic.location, center)
    stmt = select(Clinic, distance.label("distance_m")).where(ST_DWithin(Clinic.location, center, radius_km * 1000))
    if type:
        stmt = stmt.where(Clinic.type == type.value)
    stmt = stmt.order_by(distance)

    result = await db.execute(stmt)
    rows = result.all()

    clinics = []
    for clinic, distance_m in rows:
        item = ClinicResponse.model_validate(clinic)
        item.distance_km = round(distance_m / 1000, 2)
        clinics.append(item)

    return Envelope(data=clinics)
