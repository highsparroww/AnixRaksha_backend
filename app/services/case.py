from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DiseaseCase
from app.services.geo import make_point
from app.services.outbreak import evaluate_outbreak
from app.realtime.websocket import publish_event


async def create_disease_case(
    db: AsyncSession,
    disease: str,
    case_status: str,
    source: str,
    latitude: float,
    longitude: float,
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    symptom_onset: Optional[datetime] = None,
    notes: Optional[str] = None,
    reported_at: Optional[datetime] = None,
) -> DiseaseCase:
    case = DiseaseCase(
        patient_id=patient_id,
        doctor_id=doctor_id,
        clinic_id=clinic_id,
        disease=disease,
        case_status=case_status,
        source=source,
        age=age,
        gender=gender,
        location=make_point(latitude, longitude),
        latitude=latitude,
        longitude=longitude,
        symptom_onset=symptom_onset,
        notes=notes,
        reported_at=reported_at or datetime.now(timezone.utc),
    )
    db.add(case)
    await db.flush()

    await publish_event(
        "cases",
        "NEW_CASE",
        {
            "case_id": case.id,
            "disease": case.disease,
            "case_status": case.case_status,
            "latitude": round(latitude, 2),
            "longitude": round(longitude, 2),
        },
        roles=["DOCTOR", "PATIENT"],
    )
    await publish_event(
        "surveillance",
        "SURVEILLANCE_UPDATED",
        {"disease": case.disease, "latitude": round(latitude, 2), "longitude": round(longitude, 2)},
        roles=["DOCTOR", "PATIENT"],
    )

    await evaluate_outbreak(db, disease, latitude, longitude)

    return case
