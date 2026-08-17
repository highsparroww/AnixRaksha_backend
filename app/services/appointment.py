from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AppError
from app.models.enums import AppointmentStatus, NotificationType, SlotStatus
from app.models.models import Appointment, Doctor, DoctorSlot, Patient, User
from app.services.notification import create_notification
from app.realtime.websocket import publish_event
from fastapi import status


async def book_appointment(
    db: AsyncSession, patient: Patient, doctor_id: str, slot_id: str, reason: str | None
) -> Appointment:
    # Lock the slot row to avoid a race between two patients booking it at once.
    stmt = select(DoctorSlot).where(DoctorSlot.id == slot_id, DoctorSlot.doctor_id == doctor_id).with_for_update()
    result = await db.execute(stmt)
    slot = result.scalar_one_or_none()
    if not slot:
        raise AppError(status.HTTP_404_NOT_FOUND, "SLOT_NOT_FOUND", "Appointment slot not found")
    if slot.status != SlotStatus.AVAILABLE.value:
        raise AppError(status.HTTP_409_CONFLICT, "SLOT_ALREADY_BOOKED", "This appointment slot is no longer available")

    slot.status = SlotStatus.BOOKED.value
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor_id,
        slot_id=slot_id,
        status=AppointmentStatus.BOOKED.value,
        reason=reason,
    )
    db.add(appointment)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise AppError(status.HTTP_409_CONFLICT, "SLOT_ALREADY_BOOKED", "This appointment slot is no longer available")

    doctor_result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = doctor_result.scalar_one()
    patient_user_result = await db.execute(select(User).where(User.id == patient.user_id))
    patient_user = patient_user_result.scalar_one()

    await create_notification(
        db,
        user_id=doctor.user_id,
        type_=NotificationType.APPOINTMENT.value,
        title="New appointment booked",
        message=f"{patient_user.full_name} booked an appointment with you.",
        data={"appointment_id": appointment.id, "slot_id": slot_id},
    )

    await publish_event(
        "appointments",
        "APPOINTMENT_BOOKED",
        {
            "appointment_id": appointment.id,
            "doctor_id": doctor_id,
            "patient_id": patient.id,
            "slot_id": slot_id,
            "start_time": slot.start_time.isoformat(),
            "end_time": slot.end_time.isoformat(),
        },
        user_ids=[doctor.user_id],
    )

    return appointment
