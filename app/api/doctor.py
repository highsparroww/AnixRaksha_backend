from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError, get_current_doctor
from app.models.enums import CaseSource, NotificationType, SlotStatus
from app.models.models import (
    Appointment,
    Clinic,
    Doctor,
    DoctorSlot,
    DiseaseCase,
    Notification,
    Patient,
    Prediction,
    SymptomSubmission,
    User,
)
from app.schemas.schemas import (
    AppointmentDetailResponse,
    AppointmentResponse,
    DiseaseActivityResponse,
    DiseaseCaseResponse,
    DoctorCaseCreateRequest,
    DoctorCaseUpdateRequest,
    DoctorDashboardResponse,
    DoctorProfile,
    DoctorUpdateRequest,
    Envelope,
    MapCell,
    MapResponse,
    NotificationResponse,
    OutbreakAlertResponse,
    SlotCreateRequest,
    SlotResponse,
    SlotUpdateRequest,
)
from app.services.case import create_disease_case
from app.services.geo import make_point
from app.services.surveillance import get_disease_activity, get_map_data

router = APIRouter(prefix="/api/v1/doctor", tags=["doctor"])


async def _profile(db: AsyncSession, doctor: Doctor) -> DoctorProfile:
    user = (await db.execute(select(User).where(User.id == doctor.user_id))).scalar_one()
    return DoctorProfile(
        id=doctor.id,
        user_id=doctor.user_id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        specialization=doctor.specialization,
        license_number=doctor.license_number,
        clinic_id=doctor.clinic_id,
        latitude=doctor.latitude,
        longitude=doctor.longitude,
    )


@router.get("/me", response_model=Envelope[DoctorProfile])
async def get_me(db: AsyncSession = Depends(get_db), doctor: Doctor = Depends(get_current_doctor)):
    return Envelope(data=await _profile(db, doctor))


@router.put("/me", response_model=Envelope[DoctorProfile])
async def update_me(
    payload: DoctorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    user = (await db.execute(select(User).where(User.id == doctor.user_id))).scalar_one()
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.specialization is not None:
        doctor.specialization = payload.specialization
    if payload.license_number is not None:
        doctor.license_number = payload.license_number
    if payload.clinic_id is not None:
        doctor.clinic_id = payload.clinic_id
    if payload.latitude is not None and payload.longitude is not None:
        doctor.latitude = payload.latitude
        doctor.longitude = payload.longitude
        doctor.location = make_point(payload.latitude, payload.longitude)
    await db.commit()
    return Envelope(data=await _profile(db, doctor))


# ---------- Slots ----------


@router.post("/slots", response_model=Envelope[SlotResponse], status_code=status.HTTP_201_CREATED)
async def create_slot(
    payload: SlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    if payload.end_time <= payload.start_time:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_SLOT_TIME", "end_time must be after start_time")
    slot = DoctorSlot(doctor_id=doctor.id, start_time=payload.start_time, end_time=payload.end_time)
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return Envelope(data=SlotResponse.model_validate(slot))


@router.get("/slots", response_model=Envelope[list[SlotResponse]])
async def list_slots(db: AsyncSession = Depends(get_db), doctor: Doctor = Depends(get_current_doctor)):
    result = await db.execute(
        select(DoctorSlot).where(DoctorSlot.doctor_id == doctor.id).order_by(DoctorSlot.start_time)
    )
    slots = result.scalars().all()
    return Envelope(data=[SlotResponse.model_validate(s) for s in slots])


async def _get_own_slot(db: AsyncSession, doctor: Doctor, slot_id: str) -> DoctorSlot:
    result = await db.execute(select(DoctorSlot).where(DoctorSlot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot or slot.doctor_id != doctor.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "SLOT_NOT_FOUND", "Slot not found")
    return slot


@router.put("/slots/{slot_id}", response_model=Envelope[SlotResponse])
async def update_slot(
    slot_id: str,
    payload: SlotUpdateRequest,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    slot = await _get_own_slot(db, doctor, slot_id)
    if payload.start_time is not None:
        slot.start_time = payload.start_time
    if payload.end_time is not None:
        slot.end_time = payload.end_time
    if payload.status is not None:
        slot.status = payload.status.value
    await db.commit()
    await db.refresh(slot)
    return Envelope(data=SlotResponse.model_validate(slot))


@router.delete("/slots/{slot_id}", response_model=Envelope[dict])
async def delete_slot(
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    slot = await _get_own_slot(db, doctor, slot_id)
    if slot.status == SlotStatus.BOOKED.value:
        raise AppError(status.HTTP_409_CONFLICT, "SLOT_BOOKED", "Cannot delete a booked slot")
    await db.delete(slot)
    await db.commit()
    return Envelope(data={"deleted": True})


# ---------- Appointments ----------


@router.get("/appointments", response_model=Envelope[list[AppointmentResponse]])
async def list_appointments(db: AsyncSession = Depends(get_db), doctor: Doctor = Depends(get_current_doctor)):
    result = await db.execute(
        select(Appointment).where(Appointment.doctor_id == doctor.id).order_by(Appointment.created_at.desc())
    )
    items = result.scalars().all()
    return Envelope(data=[AppointmentResponse.model_validate(a) for a in items])


@router.get("/appointments/{appointment_id}", response_model=Envelope[AppointmentDetailResponse])
async def get_appointment_detail(
    appointment_id: str,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment or appointment.doctor_id != doctor.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "APPOINTMENT_NOT_FOUND", "Appointment not found")

    patient = (await db.execute(select(Patient).where(Patient.id == appointment.patient_id))).scalar_one()
    patient_user = (await db.execute(select(User).where(User.id == patient.user_id))).scalar_one()
    slot = (await db.execute(select(DoctorSlot).where(DoctorSlot.id == appointment.slot_id))).scalar_one_or_none()

    latest_submission = (
        await db.execute(
            select(SymptomSubmission)
            .where(SymptomSubmission.patient_id == patient.id)
            .order_by(SymptomSubmission.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    latest_prediction = (
        await db.execute(
            select(Prediction)
            .where(Prediction.patient_id == patient.id)
            .order_by(Prediction.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    from app.schemas.schemas import PredictionResponse

    detail = AppointmentDetailResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        slot_id=appointment.slot_id,
        status=appointment.status,
        reason=appointment.reason,
        created_at=appointment.created_at,
        patient_name=patient_user.full_name,
        patient_age=patient.age,
        patient_gender=patient.gender,
        latest_symptoms=latest_submission.symptoms if latest_submission else None,
        duration_hours=latest_submission.duration_hours if latest_submission else None,
        temperature=latest_submission.temperature if latest_submission else None,
        severity=latest_submission.severity if latest_submission else None,
        patient_notes=latest_submission.notes if latest_submission else None,
        prediction=PredictionResponse.model_validate(latest_prediction) if latest_prediction else None,
        slot=SlotResponse.model_validate(slot) if slot else None,
    )
    return Envelope(data=detail)


# ---------- Disease cases ----------


@router.post("/cases", response_model=Envelope[DiseaseCaseResponse], status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: DoctorCaseCreateRequest,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    if payload.patient_id:
        result = await db.execute(select(Patient).where(Patient.id == payload.patient_id))
        if not result.scalar_one_or_none():
            raise AppError(status.HTTP_404_NOT_FOUND, "PATIENT_NOT_FOUND", "Patient not found")

    case = await create_disease_case(
        db,
        disease=payload.disease.value,
        case_status=payload.case_status.value,
        source=CaseSource.DOCTOR.value,
        latitude=payload.latitude,
        longitude=payload.longitude,
        patient_id=payload.patient_id,
        doctor_id=doctor.id,
        clinic_id=payload.clinic_id or doctor.clinic_id,
        age=payload.age,
        gender=payload.gender.value if payload.gender else None,
        symptom_onset=payload.symptom_onset,
        notes=payload.notes,
        reported_at=payload.reported_at,
    )
    await db.commit()
    await db.refresh(case)
    return Envelope(data=DiseaseCaseResponse.model_validate(case))


@router.put("/cases/{case_id}", response_model=Envelope[DiseaseCaseResponse])
async def update_case(
    case_id: str,
    payload: DoctorCaseUpdateRequest,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    result = await db.execute(select(DiseaseCase).where(DiseaseCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case or case.doctor_id != doctor.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CASE_NOT_FOUND", "Disease case not found")
    if payload.disease is not None:
        case.disease = payload.disease.value
    if payload.case_status is not None:
        case.case_status = payload.case_status.value
    if payload.notes is not None:
        case.notes = payload.notes
    await db.commit()
    await db.refresh(case)
    return Envelope(data=DiseaseCaseResponse.model_validate(case))


@router.get("/surveillance", response_model=Envelope[DiseaseActivityResponse])
async def doctor_surveillance(
    radius_km: float = 10.0,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    if doctor.latitude is None or doctor.longitude is None:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_LOCATION", "Doctor location is not set")
    result = await get_disease_activity(db, doctor.latitude, doctor.longitude, radius_km)
    return Envelope(data=DiseaseActivityResponse(**result))


@router.get("/dashboard", response_model=Envelope[DoctorDashboardResponse])
async def dashboard(db: AsyncSession = Depends(get_db), doctor: Doctor = Depends(get_current_doctor)):
    profile = await _profile(db, doctor)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    all_appointments_result = await db.execute(
        select(Appointment, DoctorSlot)
        .join(DoctorSlot, Appointment.slot_id == DoctorSlot.id)
        .where(Appointment.doctor_id == doctor.id, Appointment.status == "BOOKED")
        .order_by(DoctorSlot.start_time)
    )
    rows = all_appointments_result.all()
    todays = [a for a, s in rows if today_start <= s.start_time < today_end]
    upcoming = [a for a, s in rows if s.start_time >= today_end]

    cases_result = await db.execute(
        select(DiseaseCase).where(DiseaseCase.doctor_id == doctor.id).order_by(DiseaseCase.created_at.desc()).limit(10)
    )
    recent_cases = list(cases_result.scalars().all())

    lat, lon = doctor.latitude, doctor.longitude
    if lat is None or lon is None:
        lat, lon = 0.0, 0.0
    activity = await get_disease_activity(db, lat, lon, 10.0)
    rising = [
        {"disease": d, **g} for d, g in activity["per_disease_growth"].items() if g["growth_percentage"] >= 30
    ]
    cells = await get_map_data(db, lat, lon, 10.0)

    from app.models.models import OutbreakAlert

    center = make_point(lat, lon)
    alerts_result = await db.execute(
        select(OutbreakAlert)
        .where(ST_DWithin(OutbreakAlert.center_location, center, 10000))
        .where(OutbreakAlert.expires_at > now)
        .order_by(OutbreakAlert.created_at.desc())
    )
    alerts = list(alerts_result.scalars().all())

    notif_result = await db.execute(
        select(Notification).where(Notification.user_id == doctor.user_id).order_by(Notification.created_at.desc()).limit(10)
    )
    notifications = list(notif_result.scalars().all())

    slots_result = await db.execute(
        select(DoctorSlot)
        .where(DoctorSlot.doctor_id == doctor.id, DoctorSlot.status == SlotStatus.AVAILABLE.value)
        .order_by(DoctorSlot.start_time)
        .limit(20)
    )
    available_slots = list(slots_result.scalars().all())

    return Envelope(
        data=DoctorDashboardResponse(
            profile=profile,
            todays_appointments=[AppointmentResponse.model_validate(a) for a in todays],
            upcoming_appointments=[AppointmentResponse.model_validate(a) for a in upcoming],
            appointment_count=len(rows),
            recent_cases=[DiseaseCaseResponse.model_validate(c) for c in recent_cases],
            disease_activity=DiseaseActivityResponse(**activity),
            rising_diseases=rising,
            outbreak_alerts=[OutbreakAlertResponse.model_validate(a) for a in alerts],
            notifications=[NotificationResponse.model_validate(n) for n in notifications],
            map=MapResponse(cells=[MapCell(**c) for c in cells]),
            available_slots=[SlotResponse.model_validate(s) for s in available_slots],
        )
    )
