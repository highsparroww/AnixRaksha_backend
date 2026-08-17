from datetime import datetime, timedelta, timezone

from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import AlertSeverity, NotificationType
from app.models.models import DiseaseCase, Notification, OutbreakAlert, Patient
from app.services.geo import make_point
from app.services.notification import create_notification
from app.services.surveillance import get_disease_activity, growth_percentage
from app.realtime.websocket import publish_event

PREVENTION_GUIDANCE = [
    "Drink only boiled, filtered, or safely bottled water.",
    "Wash hands with soap frequently, especially before eating.",
    "Avoid raw or undercooked food and unwashed produce.",
    "Avoid contact with potentially contaminated flood or stagnant water.",
    "Seek medical care promptly if symptoms like diarrhea, vomiting, or fever develop.",
]


def _severity_from_growth(growth: float, case_count: int) -> str | None:
    if growth >= settings.OUTBREAK_CRITICAL_GROWTH and case_count >= settings.OUTBREAK_CRITICAL_MIN_CASES:
        return AlertSeverity.CRITICAL.value
    if growth >= settings.OUTBREAK_HIGH_GROWTH and case_count >= settings.OUTBREAK_MIN_CASES:
        return AlertSeverity.HIGH.value
    if growth >= settings.OUTBREAK_ELEVATED_GROWTH and case_count >= settings.OUTBREAK_MIN_CASES:
        return AlertSeverity.ELEVATED.value
    if growth >= settings.OUTBREAK_WATCH_GROWTH and case_count >= settings.OUTBREAK_MIN_CASES:
        return AlertSeverity.WATCH.value
    return None


async def _has_recent_active_alert(db: AsyncSession, disease: str, latitude: float, longitude: float) -> bool:
    """Avoid spamming duplicate alerts for the same disease/area while one is
    still active."""
    now = datetime.now(timezone.utc)
    center = make_point(latitude, longitude)
    stmt = (
        select(OutbreakAlert)
        .where(OutbreakAlert.disease == disease)
        .where(OutbreakAlert.expires_at > now)
        .where(ST_DWithin(OutbreakAlert.center_location, center, settings.ALERT_RADIUS_KM * 1000))
    )
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def evaluate_outbreak(db: AsyncSession, disease: str, latitude: float, longitude: float) -> OutbreakAlert | None:
    """Run the transparent, hackathon-grade outbreak heuristic for a disease
    around a given location, using the configured ALERT_RADIUS_KM."""
    radius_km = settings.ALERT_RADIUS_KM
    activity = await get_disease_activity(db, latitude, longitude, radius_km, disease=disease)

    current = activity["cases_last_7d"]
    previous = activity["cases_previous_7d"]
    growth = activity["growth_percentage"]

    severity = _severity_from_growth(growth, current)
    if not severity:
        return None

    if await _has_recent_active_alert(db, disease, latitude, longitude):
        return None

    message = (
        f"Water-borne disease activity is {severity.lower()} in your area: "
        f"{current} {disease.replace('_', ' ').title()} case(s) reported in the last 7 days "
        f"within {int(radius_km)} km (up from {previous})."
    )

    alert = OutbreakAlert(
        disease=disease,
        center_location=make_point(latitude, longitude),
        center_latitude=latitude,
        center_longitude=longitude,
        radius_meters=radius_km * 1000,
        severity=severity,
        case_count=current,
        growth_rate=growth,
        message=message,
        prevention_guidance=PREVENTION_GUIDANCE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.OUTBREAK_ALERT_TTL_HOURS),
    )
    db.add(alert)
    await db.flush()

    await _notify_users_in_radius(db, alert)

    return alert


async def _notify_users_in_radius(db: AsyncSession, alert: OutbreakAlert) -> None:
    center = make_point(alert.center_latitude, alert.center_longitude)
    stmt = select(Patient).where(ST_DWithin(Patient.location, center, alert.radius_meters))
    result = await db.execute(stmt)
    patients = list(result.scalars().all())

    user_ids: list[str] = []
    for patient in patients:
        await create_notification(
            db,
            user_id=patient.user_id,
            type_=NotificationType.OUTBREAK_ALERT.value,
            title=f"{alert.disease.replace('_', ' ').title()} activity {alert.severity.lower()} near you",
            message=alert.message,
            data={
                "alert_id": alert.id,
                "disease": alert.disease,
                "severity": alert.severity,
                "radius_km": alert.radius_meters / 1000,
                "case_count": alert.case_count,
                "growth_rate": alert.growth_rate,
                "prevention_guidance": alert.prevention_guidance,
            },
        )
        user_ids.append(patient.user_id)

    await db.flush()

    await publish_event(
        "alerts",
        "OUTBREAK_ALERT",
        {
            "alert_id": alert.id,
            "disease": alert.disease,
            "severity": alert.severity,
            "radius_km": alert.radius_meters / 1000,
            "case_count": alert.case_count,
            "growth_rate": alert.growth_rate,
            "message": alert.message,
            "prevention_guidance": alert.prevention_guidance,
        },
        user_ids=user_ids,
        roles=["DOCTOR"],
    )
