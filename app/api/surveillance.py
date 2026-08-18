from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.enums import Disease
from app.models.models import ForecastAssessment, OutbreakAlert
from app.schemas.schemas import (
    DiseaseActivityResponse,
    Envelope,
    MapCell,
    MapResponse,
    NearbySurveillanceResponse,
    OutbreakAlertResponse,
    ForecastMapCell,
    ForecastMapResponse,
)
from app.services.surveillance import get_disease_activity, get_map_data, get_nearby_summary

router = APIRouter(prefix="/api/v1/surveillance", tags=["surveillance"])


@router.get("/forecast-map", response_model=Envelope[ForecastMapResponse])
async def forecast_map(
    db: AsyncSession = Depends(get_db), _user=Depends(get_current_user),
):
    """Separate anticipated-risk layer; never mixed into confirmed-case cells."""
    now = datetime.now(timezone.utc)
    forecasts = (await db.execute(select(ForecastAssessment).where(
        ForecastAssessment.status == "ACTIVE", ForecastAssessment.forecast_end >= now
    ).order_by(ForecastAssessment.created_at.desc()))).scalars().all()
    return Envelope(data=ForecastMapResponse(forecasts=[ForecastMapCell(
        id=item.id, disease=item.disease, latitude=item.latitude, longitude=item.longitude,
        radius_km=item.radius_km, risk_level=item.risk_level, confidence=item.confidence,
        explanation=item.explanation, forecast_start=item.forecast_start, forecast_end=item.forecast_end,
    ) for item in forecasts]))


@router.get("/nearby", response_model=Envelope[NearbySurveillanceResponse])
async def nearby(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_km: float = Query(10.0, gt=0, le=200),
    disease: Optional[Disease] = Query(None),
    time_window_days: Optional[int] = Query(7),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    # Privacy boundary: nearby surveillance exposes only aggregated counts.
    # Geographic visualization is deliberately limited to /map's coarse cells.
    summary = await get_nearby_summary(
        db, latitude, longitude, radius_km, disease.value if disease else None, time_window_days or 7
    )
    return Envelope(data=NearbySurveillanceResponse(**summary))


@router.get("/map", response_model=Envelope[MapResponse])
async def map_data(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_km: float = Query(10.0, gt=0, le=200),
    disease: Optional[Disease] = Query(None),
    time_window_days: Optional[int] = Query(7),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    cells = await get_map_data(db, latitude, longitude, radius_km, disease.value if disease else None, time_window_days)
    return Envelope(data=MapResponse(cells=[MapCell(**c) for c in cells]))


@router.get("/activity", response_model=Envelope[DiseaseActivityResponse])
async def activity(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_km: float = Query(10.0, gt=0, le=200),
    disease: Optional[Disease] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await get_disease_activity(db, latitude, longitude, radius_km, disease.value if disease else None)
    return Envelope(data=DiseaseActivityResponse(**result))


@router.get("/outbreaks", response_model=Envelope[list[OutbreakAlertResponse]])
async def outbreaks(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    radius_km: float = Query(50.0, gt=0, le=500),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    stmt = select(OutbreakAlert)
    if active_only:
        stmt = stmt.where(OutbreakAlert.expires_at > datetime.now(timezone.utc))
    stmt = stmt.order_by(OutbreakAlert.created_at.desc())
    result = await db.execute(stmt)
    alerts = list(result.scalars().all())

    if latitude is not None and longitude is not None:
        from math import asin, cos, radians, sin, sqrt

        def haversine_km(lat1, lon1, lat2, lon2):
            r = 6371
            dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 2 * r * asin(sqrt(a))

        alerts = [
            a
            for a in alerts
            if haversine_km(latitude, longitude, a.center_latitude, a.center_longitude) <= radius_km
        ]

    return Envelope(data=[OutbreakAlertResponse.model_validate(a) for a in alerts])
