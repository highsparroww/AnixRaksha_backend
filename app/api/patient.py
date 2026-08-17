from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from geoalchemy2.functions import ST_Distance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError, get_current_patient
from app.models.enums import Disease, NotificationType
from app.models.models import Appointment, Clinic, Notification, Patient, Prediction, SymptomSubmission, User
from app.schemas.schemas import (
    AppointmentCreateRequest,
    AppointmentResponse,
    ClinicResponse,
    DiseaseActivityResponse,
    Envelope,
    MapCell,
    MapResponse,
    NotificationResponse,
    OutbreakAlertResponse,
    PatientDashboardResponse,
    PatientProfile,
    PatientUpdateRequest,
    PredictionResponse,
    SymptomSubmitRequest,
)
from app.services.appointment import book_appointment
from app.services.geo import make_point
from app.services.notification import create_notification
from app.services.surveillance import get_disease_activity, get_map_data, growth_percentage

router = APIRouter(prefix="/api/v1/patient", tags=["patient"])


async def _profile(db: AsyncSession, patient: Patient) -> PatientProfile:
    user = (await db.execute(select(User).where(User.id == patient.user_id))).scalar_one()
    return PatientProfile(
        id=patient.id,
        user_id=patient.user_id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        age=patient.age,
        gender=patient.gender,
        latitude=patient.latitude,
        longitude=patient.longitude,
    )


@router.get("/me", response_model=Envelope[PatientProfile])
async def get_me(db: AsyncSession = Depends(get_db), patient: Patient = Depends(get_current_patient)):
    return Envelope(data=await _profile(db, patient))


@router.put("/me", response_model=Envelope[PatientProfile])
async def update_me(
    payload: PatientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    user = (await db.execute(select(User).where(User.id == patient.user_id))).scalar_one()
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.age is not None:
        patient.age = payload.age
    if payload.gender is not None:
        patient.gender = payload.gender.value
    if payload.latitude is not None and payload.longitude is not None:
        patient.latitude = payload.latitude
        patient.longitude = payload.longitude
        patient.location = make_point(payload.latitude, payload.longitude)
    await db.commit()
    return Envelope(data=await _profile(db, patient))


@router.post("/symptoms", response_model=Envelope[PredictionResponse], status_code=status.HTTP_201_CREATED)
async def submit_symptoms(
    payload: SymptomSubmitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    submission = SymptomSubmission(
        patient_id=patient.id,
        symptoms=[s.value for s in payload.symptoms],
        duration_hours=payload.duration_hours,
        temperature=payload.temperature,
        severity=payload.severity.value if payload.severity else None,
        notes=payload.notes,
    )
    db.add(submission)
    await db.flush()

    ml_payload = {
        "age": patient.age,
        "gender": patient.gender,
        "symptoms": submission.symptoms,
        "duration_hours": submission.duration_hours,
        "temperature": submission.temperature,
        "severity": submission.severity,
    }
    service = request.app.state.prediction_registry.service
    ml_result = await service.predict(ml_payload)

    prediction = Prediction(
        patient_id=patient.id,
        symptom_submission_id=submission.id,
        predicted_disease=ml_result["predicted_disease"],
        is_water_borne=ml_result["is_water_borne"],
        confidence=ml_result["confidence"],
        model_version=ml_result["model_version"],
        reference_input=ml_payload,
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)

    return Envelope(data=PredictionResponse.model_validate(prediction))


@router.get("/predictions", response_model=Envelope[list[PredictionResponse]])
async def prediction_history(db: AsyncSession = Depends(get_db), patient: Patient = Depends(get_current_patient)):
    result = await db.execute(
        select(Prediction).where(Prediction.patient_id == patient.id).order_by(Prediction.created_at.desc())
    )
    items = result.scalars().all()
    return Envelope(data=[PredictionResponse.model_validate(p) for p in items])


@router.get("/appointments", response_model=Envelope[list[AppointmentResponse]])
async def list_appointments(db: AsyncSession = Depends(get_db), patient: Patient = Depends(get_current_patient)):
    result = await db.execute(
        select(Appointment).where(Appointment.patient_id == patient.id).order_by(Appointment.created_at.desc())
    )
    items = result.scalars().all()
    return Envelope(data=[AppointmentResponse.model_validate(a) for a in items])


@router.post("/appointments", response_model=Envelope[AppointmentResponse], status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    appointment = await book_appointment(db, patient, payload.doctor_id, payload.slot_id, payload.reason)
    await db.commit()
    await db.refresh(appointment)
    return Envelope(data=AppointmentResponse.model_validate(appointment))


@router.get("/disease-activity", response_model=Envelope[DiseaseActivityResponse])
async def disease_activity(
    radius_km: float = Query(10.0, gt=0, le=200),
    disease: Optional[Disease] = Query(None),
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    if patient.latitude is None or patient.longitude is None:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_LOCATION", "Patient location is not set")
    result = await get_disease_activity(
        db, patient.latitude, patient.longitude, radius_km, disease.value if disease else None
    )
    return Envelope(data=DiseaseActivityResponse(**result))


@router.get("/nearby-clinics", response_model=Envelope[list[ClinicResponse]])
async def nearby_clinics(
    radius_km: float = Query(10.0, gt=0, le=200),
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    if patient.latitude is None or patient.longitude is None:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_LOCATION", "Patient location is not set")
    from geoalchemy2.functions import ST_DWithin

    center = make_point(patient.latitude, patient.longitude)
    distance = ST_Distance(Clinic.location, center)
    stmt = (
        select(Clinic, distance.label("distance_m"))
        .where(ST_DWithin(Clinic.location, center, radius_km * 1000))
        .order_by(distance)
    )
    result = await db.execute(stmt)
    clinics = []
    for clinic, distance_m in result.all():
        item = ClinicResponse.model_validate(clinic)
        item.distance_km = round(distance_m / 1000, 2)
        clinics.append(item)
    return Envelope(data=clinics)


@router.get("/dashboard", response_model=Envelope[PatientDashboardResponse])
async def dashboard(db: AsyncSession = Depends(get_db), patient: Patient = Depends(get_current_patient)):
    profile = await _profile(db, patient)

    lat, lon = patient.latitude, patient.longitude
    if lat is None or lon is None:
        lat, lon = 0.0, 0.0

    activity = await get_disease_activity(db, lat, lon, 10.0)
    rising = [
        {"disease": d, **g}
        for d, g in activity["per_disease_growth"].items()
        if g["growth_percentage"] >= 30
    ]
    cells = await get_map_data(db, lat, lon, 10.0)

    from app.models.models import OutbreakAlert
    from geoalchemy2.functions import ST_DWithin

    center = make_point(lat, lon)
    alerts_result = await db.execute(
        select(OutbreakAlert)
        .where(ST_DWithin(OutbreakAlert.center_location, center, 10000))
        .where(OutbreakAlert.expires_at > datetime.now(timezone.utc))
        .order_by(OutbreakAlert.created_at.desc())
    )
    alerts = list(alerts_result.scalars().all())

    upcoming_result = await db.execute(
        select(Appointment)
        .where(Appointment.patient_id == patient.id, Appointment.status == "BOOKED")
        .order_by(Appointment.created_at.desc())
        .limit(5)
    )
    upcoming = list(upcoming_result.scalars().all())

    notif_result = await db.execute(
        select(Notification).where(Notification.user_id == patient.user_id).order_by(Notification.created_at.desc()).limit(10)
    )
    notifications = list(notif_result.scalars().all())
    unread_count = sum(1 for n in notifications if not n.is_read)

    clinics_result = await db.execute(
        select(Clinic, ST_Distance(Clinic.location, center).label("distance_m"))
        .order_by(ST_Distance(Clinic.location, center))
        .limit(5)
    )
    clinics = []
    for clinic, distance_m in clinics_result.all():
        item = ClinicResponse.model_validate(clinic)
        item.distance_km = round(distance_m / 1000, 2)
        clinics.append(item)

    predictions_result = await db.execute(
        select(Prediction).where(Prediction.patient_id == patient.id).order_by(Prediction.created_at.desc()).limit(5)
    )
    predictions = list(predictions_result.scalars().all())

    return Envelope(
        data=PatientDashboardResponse(
            profile=profile,
            disease_activity=DiseaseActivityResponse(**activity),
            rising_diseases=rising,
            outbreak_alerts=[OutbreakAlertResponse.model_validate(a) for a in alerts],
            map=MapResponse(cells=[MapCell(**c) for c in cells]),
            upcoming_appointments=[AppointmentResponse.model_validate(a) for a in upcoming],
            unread_notification_count=unread_count,
            notifications=[NotificationResponse.model_validate(n) for n in notifications],
            nearby_clinics=clinics,
            recent_predictions=[PredictionResponse.model_validate(p) for p in predictions],
        )
    )
