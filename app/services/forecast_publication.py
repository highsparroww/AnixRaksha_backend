"""Automatic publication boundary for future model outputs.

The model is deliberately external to this module. Once a validated model
produces a forecast, publishing it updates the predicted-risk layer and sends
location-based notifications without affecting confirmed-case surveillance.
"""

from datetime import datetime

from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.models import ForecastAssessment, Patient
from app.services.geo import make_point
from app.services.notification import create_notification


async def publish_forecast(
    db: AsyncSession, *, disease: str, latitude: float, longitude: float,
    radius_km: float, risk_level: str, confidence: float, model_version: str,
    explanation: dict, evidence_context: dict, forecast_start: datetime, forecast_end: datetime,
) -> ForecastAssessment:
    assessment = ForecastAssessment(
        disease=disease, latitude=latitude, longitude=longitude, radius_km=radius_km,
        risk_level=risk_level, confidence=confidence, model_version=model_version,
        explanation=explanation, evidence_context=evidence_context,
        forecast_start=forecast_start, forecast_end=forecast_end, status="ACTIVE",
    )
    db.add(assessment)
    await db.flush()
    patients = (await db.execute(select(Patient).where(
        ST_DWithin(Patient.location, make_point(latitude, longitude), radius_km * 1000)
    ))).scalars().all()
    for patient in patients:
        await create_notification(
            db, patient.user_id, NotificationType.FORECAST_ALERT.value,
            f"Anticipated {disease.replace('_', ' ').title()} risk near you",
            "A forecast indicates elevated disease risk in your area. Follow local health guidance.",
            data={"forecast_id": assessment.id, "disease": disease, "risk_level": risk_level,
                  "confidence": confidence, "forecast_start": forecast_start.isoformat(), "forecast_end": forecast_end.isoformat()},
        )
    return assessment
