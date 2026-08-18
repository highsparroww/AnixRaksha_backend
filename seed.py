"""Seed WaterWatch with demo data: admin, doctors, patients, clinics, slots,
appointments, predictions, notifications, and disease cases (including one
clustered area for the map demo).

Run with:
    python3 seed.py
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.database import AsyncSessionLocal
from app.models.enums import (
    AppointmentStatus,
    CaseSource,
    CaseStatus,
    ClinicType,
    Disease,
    Gender,
    NotificationType,
    SlotStatus,
    UserRole,
)
from app.models.models import (
    Appointment,
    Clinic,
    Doctor,
    DoctorSlot,
    DiseaseCase,
    HealthConversation,
    HealthIntake,
    Notification,
    Patient,
    Prediction,
    SymptomSubmission,
    User,
    UserSession,
)
from app.security import hash_password
from app.services.geo import make_point

# Center the demo around Kanpur, India, with a clustered outbreak area nearby.
CITY_LAT, CITY_LON = 26.4499, 80.3319
CLUSTER_LAT, CLUSTER_LON = 26.47, 80.35  # ~3km away, inside a 10km alert radius


async def clear_all(session):
    for model in [
        Notification,
        Prediction,
        SymptomSubmission,
        DiseaseCase,
        Appointment,
        HealthConversation,
        HealthIntake,
        DoctorSlot,
        Doctor,
        Patient,
        Clinic,
        UserSession,
        User,
    ]:
        await session.execute(model.__table__.delete())
    await session.commit()


def jitter(lat, lon, km=2.0):
    d = km / 111.0
    return lat + random.uniform(-d, d), lon + random.uniform(-d, d)


async def seed():
    async with AsyncSessionLocal() as session:
        await clear_all(session)

        # ---------- Admin ----------
        admin = User(
            email="admin@waterwatch.dev",
            hashed_password=hash_password("Admin123!"),
            role=UserRole.ADMIN.value,
            full_name="System Admin",
            phone="+910000000000",
        )
        session.add(admin)

        # ---------- Clinics ----------
        clinic_defs = [
            ("Kanpur General Hospital", ClinicType.GOVERNMENT, CITY_LAT + 0.01, CITY_LON + 0.01),
            ("District Government Clinic", ClinicType.GOVERNMENT, CITY_LAT - 0.02, CITY_LON + 0.02),
            ("Sunshine Private Clinic", ClinicType.PRIVATE, CITY_LAT + 0.03, CITY_LON - 0.01),
            ("CarePlus Multispecialty", ClinicType.PRIVATE, CITY_LAT - 0.01, CITY_LON - 0.03),
            ("Riverside Community Health Center", ClinicType.GOVERNMENT, CLUSTER_LAT, CLUSTER_LON + 0.01),
        ]
        clinics = []
        for name, ctype, lat, lon in clinic_defs:
            clinic = Clinic(
                name=name,
                type=ctype.value,
                address=f"{name}, Kanpur, UP, India",
                phone=f"+91-512-{random.randint(1000000, 9999999)}",
                location=make_point(lat, lon),
                latitude=lat,
                longitude=lon,
                opening_time="08:00",
                closing_time="20:00",
            )
            clinics.append(clinic)
            session.add(clinic)
        await session.flush()

        # ---------- Doctors ----------
        doctor_defs = [
            ("Dr. Asha Verma", "General Physician", clinics[0]),
            ("Dr. Rohit Mehta", "Infectious Disease Specialist", clinics[1]),
            ("Dr. Priya Nair", "Pediatrician", clinics[4]),
        ]
        doctors = []
        for i, (name, spec, clinic) in enumerate(doctor_defs):
            user = User(
                email=f"doctor{i+1}@waterwatch.dev",
                hashed_password=hash_password("Doctor123!"),
                role=UserRole.DOCTOR.value,
                full_name=name,
                phone=f"+91-98{random.randint(10000000, 99999999)}",
            )
            session.add(user)
            await session.flush()
            doctor = Doctor(
                user_id=user.id,
                specialization=spec,
                license_number=f"LIC-{1000 + i}",
                clinic_id=clinic.id,
                latitude=clinic.latitude,
                longitude=clinic.longitude,
                location=make_point(clinic.latitude, clinic.longitude),
            )
            session.add(doctor)
            doctors.append(doctor)
        await session.flush()

        # ---------- Doctor slots (next 3 days, 15-min increments) ----------
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        all_slots = []
        for doctor in doctors:
            for day in range(3):
                day_start = now + timedelta(days=day, hours=9 - now.hour if now.hour < 9 else 24 - now.hour + 9)
                for i in range(8):  # 8 slots per day
                    start = day_start + timedelta(minutes=15 * i)
                    end = start + timedelta(minutes=15)
                    slot = DoctorSlot(doctor_id=doctor.id, start_time=start, end_time=end)
                    session.add(slot)
                    all_slots.append(slot)
        await session.flush()

        # ---------- Patients ----------
        patient_names = [
            "Aarav Sharma", "Diya Patel", "Kabir Singh", "Ananya Gupta", "Vivaan Kumar",
            "Ishita Joshi", "Reyansh Yadav", "Myra Chauhan", "Aditya Rao", "Saanvi Mishra",
        ]
        patients = []
        for i, name in enumerate(patient_names):
            lat, lon = jitter(CITY_LAT, CITY_LON, km=4.0)
            user = User(
                email=f"patient{i+1}@waterwatch.dev",
                hashed_password=hash_password("Patient123!"),
                role=UserRole.PATIENT.value,
                full_name=name,
                phone=f"+91-70{random.randint(10000000, 99999999)}",
            )
            session.add(user)
            await session.flush()
            patient = Patient(
                user_id=user.id,
                age=random.randint(5, 70),
                gender=random.choice([g.value for g in Gender]),
                latitude=lat,
                longitude=lon,
                location=make_point(lat, lon),
            )
            session.add(patient)
            patients.append(patient)
        await session.flush()

        # A couple of patients live right inside the cluster so they receive the outbreak alert.
        for patient in patients[:3]:
            lat, lon = jitter(CLUSTER_LAT, CLUSTER_LON, km=1.5)
            patient.latitude, patient.longitude = lat, lon
            patient.location = make_point(lat, lon)
        await session.flush()

        # ---------- Symptom submissions + predictions ----------
        symptom_sets = [
            ["DIARRHEA", "VOMITING", "FEVER"],
            ["FEVER", "HEADACHE", "WEAKNESS"],
            ["DIARRHEA", "DEHYDRATION"],
            ["NAUSEA", "ABDOMINAL_PAIN"],
        ]
        disease_map = {
            "DIARRHEA": Disease.CHOLERA,
            "FEVER": Disease.TYPHOID,
            "NAUSEA": Disease.HEPATITIS_A,
        }
        for patient in patients[:6]:
            symptoms = random.choice(symptom_sets)
            submission = SymptomSubmission(
                patient_id=patient.id,
                symptoms=symptoms,
                duration_hours=random.choice([12, 24, 48, 72]),
                temperature=round(random.uniform(37.0, 39.5), 1),
                severity=random.choice(["MILD", "MODERATE", "SEVERE"]),
                notes="Seed demo data",
            )
            session.add(submission)
            await session.flush()

            predicted = next((d for s, d in disease_map.items() if s in symptoms), Disease.OTHER_WATER_BORNE)
            prediction = Prediction(
                patient_id=patient.id,
                symptom_submission_id=submission.id,
                predicted_disease=predicted.value,
                is_water_borne=True,
                confidence=round(random.uniform(0.55, 0.92), 2),
                model_version="mock-v1",
                reference_input={"symptoms": symptoms},
            )
            session.add(prediction)
        await session.flush()

        # ---------- Appointments (book a few slots) ----------
        booked_slots = random.sample(all_slots, k=6)
        for i, slot in enumerate(booked_slots):
            patient = patients[i % len(patients)]
            slot.status = SlotStatus.BOOKED.value
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=slot.doctor_id,
                slot_id=slot.id,
                status=AppointmentStatus.BOOKED.value,
                reason="Feeling unwell, requesting checkup",
            )
            session.add(appointment)
        await session.flush()

        # ---------- Disease cases: scattered baseline + one clustered area ----------
        # Baseline scattered cases across the city (registered + unregistered patients)
        for _ in range(10):
            lat, lon = jitter(CITY_LAT, CITY_LON, km=6.0)
            disease = random.choice([d.value for d in Disease])
            patient = random.choice(patients) if random.random() > 0.4 else None
            case = DiseaseCase(
                patient_id=patient.id if patient else None,
                doctor_id=random.choice(doctors).id,
                clinic_id=random.choice(clinics).id,
                disease=disease,
                case_status=random.choice([CaseStatus.SUSPECTED.value, CaseStatus.PROBABLE.value, CaseStatus.CONFIRMED.value]),
                source=CaseSource.DOCTOR.value if patient else CaseSource.DOCTOR.value,
                age=random.randint(5, 70),
                gender=random.choice([g.value for g in Gender]),
                location=make_point(lat, lon),
                latitude=lat,
                longitude=lon,
                reported_at=datetime.now(timezone.utc) - timedelta(days=random.uniform(8, 20)),
                notes="Seed baseline case",
            )
            session.add(case)

        # Clustered recent CHOLERA cases -> should show elevated activity on the map/demo
        for _ in range(9):
            lat, lon = jitter(CLUSTER_LAT, CLUSTER_LON, km=1.2)
            patient = random.choice(patients) if random.random() > 0.6 else None
            case = DiseaseCase(
                patient_id=patient.id if patient else None,
                doctor_id=doctors[1].id,
                clinic_id=clinics[4].id,
                disease=Disease.CHOLERA.value,
                case_status=CaseStatus.CONFIRMED.value,
                source=CaseSource.DOCTOR.value,
                age=random.randint(5, 70),
                gender=random.choice([g.value for g in Gender]),
                location=make_point(lat, lon),
                latitude=lat,
                longitude=lon,
                reported_at=datetime.now(timezone.utc) - timedelta(hours=random.uniform(0, 96)),
                notes="Seed clustered cholera case (for outbreak/map demo)",
            )
            session.add(case)
        await session.flush()

        # ---------- Notifications ----------
        for patient in patients[:4]:
            notification = Notification(
                user_id=patient.user_id,
                type=NotificationType.SYSTEM.value,
                title="Welcome to WaterWatch",
                message="Thanks for joining WaterWatch. Keep your location updated for the best local alerts.",
                data=None,
                is_read=random.choice([True, False]),
            )
            session.add(notification)

        await session.commit()

        print("Seed complete.")
        print(f"  Admin:    admin@waterwatch.dev / Admin123!")
        print(f"  Doctors:  doctor1..3@waterwatch.dev / Doctor123!")
        print(f"  Patients: patient1..10@waterwatch.dev / Patient123!")
        print(f"  Cluster center for outbreak demo: {CLUSTER_LAT}, {CLUSTER_LON}")
        print(f"  City center: {CITY_LAT}, {CITY_LON}")


if __name__ == "__main__":
    asyncio.run(seed())
