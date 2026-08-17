from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError, get_current_patient
from app.models.enums import AlertSeverity, NotificationType
from app.models.models import Notification, Patient
from app.schemas.schemas import Envelope, EnvironmentalRiskResponse
from app.services.notification import create_notification

router = APIRouter(prefix="/api/v1/environmental-risk", tags=["environmental risk"])


@router.get("/me", response_model=Envelope[EnvironmentalRiskResponse])
async def assess_my_area(
    request: Request,
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    """Evaluate the current patient's approximate area using the configured
    environmental ML service and notify them for elevated or higher risk."""
    if patient.latitude is None or patient.longitude is None:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_LOCATION", "Patient location is not set")

    try:
        result = await request.app.state.environmental_risk_registry.service.assess(
            patient.latitude, patient.longitude
        )
    except httpx.HTTPError as exc:
        # A model/data-provider outage must not appear as an application crash.
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ENVIRONMENTAL_RISK_SERVICE_UNAVAILABLE",
            "Environmental risk data is temporarily unavailable. Please try again later.",
        ) from exc

    try:
        assessment = EnvironmentalRiskResponse.model_validate(result)
    except ValidationError as exc:
        raise AppError(
            status.HTTP_502_BAD_GATEWAY,
            "INVALID_ENVIRONMENTAL_RISK_RESPONSE",
            "The environmental risk service returned an invalid assessment.",
        ) from exc

    if assessment.risk_level in {AlertSeverity.ELEVATED, AlertSeverity.HIGH, AlertSeverity.CRITICAL}:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        existing = await db.execute(
            select(Notification.id)
            .where(Notification.user_id == patient.user_id)
            .where(Notification.type == NotificationType.ENVIRONMENTAL_RISK.value)
            .where(Notification.created_at >= since)
            .limit(1)
        )
        if existing.scalar_one_or_none() is None:
            factors = ", ".join(item.factor.replace("_", " ").lower() for item in assessment.contributing_factors)
            await create_notification(
                db,
                patient.user_id,
                NotificationType.ENVIRONMENTAL_RISK.value,
                "Environmental health risk in your area",
                f"{assessment.risk_level.value.title()} risk identified. Factors: {factors or 'environmental conditions'}.",
                data=assessment.model_dump(mode="json"),
            )
            await db.commit()

    return Envelope(data=assessment)
