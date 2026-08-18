"""Government-only collection and review boundary for future forecasting."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.models import ForecastAssessment, SurveillanceSignal, User
from app.schemas.schemas import (
    Envelope, ForecastAssessmentResponse,
    SurveillanceSignalCreateRequest, SurveillanceSignalResponse,
)
from app.services.geo import make_point

router = APIRouter(prefix="/api/v1/government", tags=["government surveillance"])


@router.post("/signals", response_model=Envelope[SurveillanceSignalResponse], status_code=status.HTTP_201_CREATED)
async def collect_signal(
    payload: SurveillanceSignalCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("GOVERNMENT", "ADMIN")),
):
    signal = SurveillanceSignal(
        signal_type=payload.signal_type.value, disease=payload.disease.value if payload.disease else None,
        source=payload.source, latitude=payload.latitude, longitude=payload.longitude,
        location=make_point(payload.latitude, payload.longitude), observed_at=payload.observed_at,
        data=payload.data, collected_by_user_id=user.id,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return Envelope(data=SurveillanceSignalResponse.model_validate(signal))


@router.get("/forecast-assessments", response_model=Envelope[list[ForecastAssessmentResponse]])
async def list_forecast_assessments(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("GOVERNMENT", "ADMIN")),
):
    stmt = select(ForecastAssessment).order_by(ForecastAssessment.created_at.desc())
    return Envelope(data=[ForecastAssessmentResponse.model_validate(item) for item in (await db.execute(stmt)).scalars().all()])
